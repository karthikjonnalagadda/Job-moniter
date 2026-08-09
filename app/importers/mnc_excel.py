"""MNC career-site Excel importer.

Integrates ``India_MNC_Career_Sites_Master_2026.xlsx`` (sheet ``MNC Career
Sites``) into the existing company database *without* creating a parallel
pipeline. It maps the Excel columns onto the project's two operative schemas,
runs the existing ``ATSDetector`` on every career URL, normalises URLs, and
deduplicates against what already exists by normalised name, alias, and domain.

Two write targets (both consumed by the existing framework):

* ``indian_company_metadata.yaml`` - the **runtime seed** that
  ``IndiaSeedBuilder`` -> ``CompanyImportService`` load into MongoDB. New MNCs
  are appended here so they become *first-class* pipeline sources (routed to
  collectors, collected, ranked, reported) - not merely catalogued.
* ``indian_companies.{json,yaml,csv}`` - the published **1,408-company master**
  (25-field schema). Existing matches are enriched (blank-fill only, never
  clobbered); genuinely new companies are appended.

This module is pure/deterministic (no network, no clock beyond an injected
``today``) so it is unit-testable and produces stable diffs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from app.core.text import slugify
from app.routing.detector import ATSDetection, ATSDetector

# --------------------------------------------------------------------------
# Excel column names (sheet: "MNC Career Sites")
# --------------------------------------------------------------------------
SHEET_NAME = "MNC Career Sites"
COL_COMPANY = "Company"
COL_SECTOR = "Sector"
COL_HQ = "HQ"
COL_PRIORITY = "India Opportunity Priority"
COL_RELEVANCE = "AI/ML & Data Relevance"
COL_FRESHER = "Fresher / 0-2 YOE Potential"
COL_URL = "Official Careers URL"
COL_URL_CONF = "URL Confidence"
COL_KEYWORDS = "India Search Keywords"
COL_NOTES = "Notes"
COL_RECOMMENDED = "Recommended for AI/Data Profile"

# --------------------------------------------------------------------------
# Value mappings
# --------------------------------------------------------------------------
# Excel Sector -> CompanyCategory enum value (see app.models.enums.CompanyCategory).
SECTOR_TO_CATEGORY: dict[str, str] = {
    "Big Tech & Product": "product",
    "Banking & Financial Services": "bfsi",
    "Industrial, Engineering & Energy": "manufacturing",
    "IT Services & Consulting": "it_services",
    "Healthcare, Pharma & MedTech": "pharma",
    "Automotive & Mobility": "automotive",
    "FMCG, Retail & Consumer": "retail",
    "Consulting & Professional Services": "consulting",
    "Semiconductors & Electronics": "manufacturing",
    "Telecom, Media & Entertainment": "telecom",
    "Logistics, Travel & Aviation": "other",
    "Insurance": "bfsi",
    "Real Estate, Infrastructure & Services": "other",
    "Food, Agriculture & Chemicals": "other",
}

# HQ country name -> ISO-3166 alpha-2 (matches existing dataset's "IN" convention).
HQ_TO_ISO: dict[str, str] = {
    "USA": "US", "UK": "GB", "Germany": "DE", "Japan": "JP", "France": "FR",
    "India": "IN", "Switzerland": "CH", "Netherlands": "NL", "Canada": "CA",
    "Ireland": "IE", "Taiwan": "TW", "Singapore": "SG", "South Korea": "KR",
    "Australia": "AU", "Sweden": "SE", "Denmark": "DK", "Luxembourg": "LU",
    "UAE": "AE", "Finland": "FI", "China": "CN", "Belgium": "BE", "Brazil": "BR",
    "Norway": "NO", "Italy": "IT", "Qatar": "QA", "Spain": "ES",
}

# Standard target-profile roles/tech applied to new MNC records. Company-level
# metadata only - it never overrides job-level eligibility (the pipeline filters
# still gate every posting on title/seniority/experience).
STANDARD_ROLES: tuple[str, ...] = (
    "AI Engineer", "Machine Learning Engineer", "Data Scientist",
    "Data Engineer", "Data Analyst", "Software Engineer", "Backend Engineer",
)
STANDARD_TECHS: tuple[str, ...] = (
    "Python", "Machine Learning", "SQL", "Cloud", "Data Engineering",
)

# Query-string keys that are tracking noise and must be stripped from URLs.
_TRACKING_PREFIXES = ("utm_",)
_TRACKING_KEYS = frozenset(
    {"gclid", "fbclid", "mc_cid", "mc_eid", "ref", "source", "src", "cmp",
     "campaign", "medium"}
)

# Multi-label public suffixes needed to derive a registrable domain for dedup.
_TWO_LEVEL_TLDS = frozenset(
    {"co.uk", "co.in", "com.au", "co.jp", "com.br", "co.kr", "com.sg",
     "com.cn", "co.za", "com.mx", "co.nz"}
)


def registrable_domain(url: str | None) -> str:
    """Return the registrable domain (``bmwgroup.jobs``) for dedup, or ""."""

    if not url:
        return ""
    host = urlparse(url if "://" in url else f"https://{url}").netloc.lower()
    host = host.split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    labels = [label for label in host.split(".") if label]
    if len(labels) < 2:
        return host
    last_two = ".".join(labels[-2:])
    last_three = ".".join(labels[-3:]) if len(labels) >= 3 else ""
    if last_two in _TWO_LEVEL_TLDS and last_three:
        return last_three
    return last_two


def normalize_url(url: str | None) -> str:
    """Normalise a career URL: lowercase host, drop fragment + tracking params.

    Non-tracking query parameters are preserved (some ATS URLs encode the board
    there). Returns "" for anything that is not a well-formed http(s) URL.
    """

    if not url:
        return ""
    raw = str(url).strip()
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    if "." not in parsed.netloc:
        return ""
    host = parsed.netloc.lower()
    kept = [
        pair
        for pair in parsed.query.split("&")
        if pair
        and not pair.split("=", 1)[0].lower().startswith(_TRACKING_PREFIXES)
        and pair.split("=", 1)[0].lower() not in _TRACKING_KEYS
    ]
    query = "&".join(kept)
    path = parsed.path or "/"
    return urlunparse((parsed.scheme, host, path, "", query, ""))


# Legal/entity suffixes stripped when comparing company names for dedup.
_NAME_STOPWORDS = frozenset(
    {"inc", "incorporated", "corp", "corporation", "co", "company", "ltd",
     "limited", "plc", "llc", "llp", "gmbh", "ag", "sa", "nv", "spa", "ab",
     "oyj", "as", "bv", "group", "holdings", "holding", "technologies",
     "technology", "systems", "solutions", "labs", "the", "and", "&",
     "india", "global", "international", "worldwide"}
)


def normalize_name(name: str) -> str:
    """Aggressively normalise a company name for matching (not for display)."""

    slug = slugify(name)  # ascii, lowercase, hyphenated; "&" -> "and"
    tokens = [t for t in slug.split("-") if t and t not in _NAME_STOPWORDS]
    return "".join(tokens)


@dataclass(frozen=True)
class MncRow:
    """One validated row from the Excel sheet, with mapped/derived values."""

    company: str
    sector: str
    hq: str
    priority: str          # "Tier 1" | "Tier 2"
    relevance: str         # "High" | "Medium"
    fresher: str           # "Strong" | "Possible"
    url_raw: str
    url: str               # normalised
    url_confidence: str    # "High" | "Verify"
    keywords: str
    notes: str
    recommended: str       # "YES" | "Monitor"
    detection: ATSDetection

    @property
    def slug(self) -> str:
        return slugify(self.company)

    @property
    def norm_name(self) -> str:
        return normalize_name(self.company)

    @property
    def domain(self) -> str:
        return registrable_domain(self.url)

    @property
    def url_verified(self) -> bool:
        return self.url_confidence.strip().lower() == "high" and bool(self.url)

    @property
    def is_recommended(self) -> bool:
        return self.recommended.strip().upper() == "YES"


@dataclass
class MergeStats:
    existing_master: int = 0
    excel_rows: int = 0
    new_to_master: int = 0
    enriched_master: int = 0
    duplicates: int = 0            # excel rows already present in master
    new_to_runtime: int = 0        # appended to metadata.yaml
    already_runtime: int = 0
    urls_verified: int = 0
    urls_to_verify: int = 0
    urls_malformed: int = 0
    ats_breakdown: dict[str, int] = field(default_factory=dict)
    manual_review: list[str] = field(default_factory=list)

    @property
    def master_final(self) -> int:
        return self.existing_master + self.new_to_master


class MncExcelReader:
    """Reads and validates the MNC Excel sheet into ``MncRow`` records."""

    def __init__(self, detector: ATSDetector | None = None) -> None:
        self._detector = detector or ATSDetector()

    def read(self, path: Path) -> list[MncRow]:
        import openpyxl  # local import: heavy, only needed for the read

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        if SHEET_NAME not in wb.sheetnames:
            raise ValueError(f"Sheet '{SHEET_NAME}' not found in {path.name}")
        ws = wb[SHEET_NAME]
        rows = ws.iter_rows(values_only=True)
        header = [str(c).strip() if c is not None else "" for c in next(rows)]
        idx = {name: header.index(name) for name in header if name}
        required = (COL_COMPANY, COL_URL)
        for col in required:
            if col not in idx:
                raise ValueError(f"Required column '{col}' missing from sheet")

        def cell(row: tuple[Any, ...], col: str) -> str:
            i = idx.get(col)
            if i is None or i >= len(row) or row[i] is None:
                return ""
            return str(row[i]).strip()

        out: list[MncRow] = []
        seen_slugs: set[str] = set()
        for row in rows:
            company = cell(row, COL_COMPANY)
            if not company:
                continue
            slug = slugify(company)
            if slug in seen_slugs:  # in-file dedup
                continue
            seen_slugs.add(slug)
            url = normalize_url(cell(row, COL_URL))
            out.append(
                MncRow(
                    company=company,
                    sector=cell(row, COL_SECTOR),
                    hq=cell(row, COL_HQ),
                    priority=cell(row, COL_PRIORITY),
                    relevance=cell(row, COL_RELEVANCE),
                    fresher=cell(row, COL_FRESHER),
                    url_raw=cell(row, COL_URL),
                    url=url,
                    url_confidence=cell(row, COL_URL_CONF),
                    keywords=cell(row, COL_KEYWORDS),
                    notes=cell(row, COL_NOTES),
                    recommended=cell(row, COL_RECOMMENDED),
                    detection=self._detector.detect(url),
                )
            )
        return out


# --------------------------------------------------------------------------
# Field mapping helpers
# --------------------------------------------------------------------------
def _ai_score_100(relevance: str) -> int:
    return {"high": 85, "medium": 65, "low": 45}.get(relevance.strip().lower(), 55)


def _ai_score_10(relevance: str) -> int:
    return {"high": 9, "medium": 7, "low": 5}.get(relevance.strip().lower(), 6)


def _priority_score(priority: str, relevance: str) -> int:
    tier1 = priority.strip().lower() == "tier 1"
    high = relevance.strip().lower() == "high"
    if tier1 and high:
        return 90
    if tier1:
        return 82
    if high:
        return 72
    return 64


def _freshers_flag(fresher: str) -> str:
    return {"strong": "Yes", "possible": "Possible"}.get(fresher.strip().lower(), "Unknown")


def _career_status(url_confidence: str, has_url: bool) -> str:
    if not has_url:
        return "no_url"
    return "working" if url_confidence.strip().lower() == "high" else "unverified"


def metadata_record(row: MncRow) -> dict[str, Any]:
    """Build a runtime-seed record (``indian_company_metadata.yaml`` schema)."""

    det = row.detection
    iso = HQ_TO_ISO.get(row.hq, "")
    notes = row.notes or ""
    tag = "MNC GCC/global careers portal (Excel MNC master 2026)."
    return {
        "name": row.company,
        "slug": row.slug,
        "career_url": row.url or None,
        "industry": row.sector or None,
        "headquarters": row.hq or None,
        "country": iso or None,
        "company_category": SECTOR_TO_CATEGORY.get(row.sector, "unknown"),
        "ats_type": det.ats_type.value if det.detected else "unknown",
        "ats_token": det.token if det.detected else None,
        "career_platform": det.platform if det.detected else "Custom",
        "priority_score": _priority_score(row.priority, row.relevance),
        "ai_hiring_score": _ai_score_100(row.relevance),
        "remote_support": False,
        "crawl_frequency": "weekly",
        "supported_roles": list(STANDARD_ROLES),
        "preferred_technologies": list(STANDARD_TECHS),
        "aliases": [],
        "notes": f"{notes} {tag}".strip(),
    }


def master_record(row: MncRow, today: str) -> dict[str, Any]:
    """Build a published-master record (``indian_companies.*`` 25-field schema)."""

    det = row.detection
    website = ""
    if row.url:
        parsed = urlparse(row.url)
        website = f"{parsed.scheme}://{parsed.netloc}/"
    return {
        "company_name": row.company,
        "career_url": row.url,
        "website": website,
        "industry": row.sector,
        "category": SECTOR_TO_CATEGORY.get(row.sector, "unknown"),
        "country": HQ_TO_ISO.get(row.hq, ""),
        "state": "Unknown",
        "headquarters": row.hq,
        "company_size": "large",
        "founded_year": "Unknown",
        "ats_platform": det.ats_type.value if det.detected else "Unknown",
        "ats_token": det.token if det.detected else "Unknown",
        "ats_confidence": round(det.confidence, 2) if det.detected else 0,
        "ats_detection_method": "url_pattern" if det.detected else "none",
        "internship_available": "Unknown",
        "graduate_program": "Unknown",
        "freshers_hiring": _freshers_flag(row.fresher),
        "remote_friendly": "Unknown",
        "ai_hiring_score": _ai_score_10(row.relevance),
        "hiring_frequency": "Unknown",
        "preferred_roles": list(STANDARD_ROLES),
        "preferred_technologies": list(STANDARD_TECHS),
        "tech_stack": list(STANDARD_TECHS),
        "career_status": _career_status(row.url_confidence, bool(row.url)),
        "last_verified_date": today if row.url_verified else "",
        # ---- New provenance columns (Excel MNC master) ----
        "india_priority": row.priority,
        "ai_data_relevance": row.relevance,
        "fresher_potential": row.fresher,
        "url_confidence": row.url_confidence,
        "recommended_for_ai_data": "YES" if row.is_recommended else "Monitor",
        "source": "mnc_excel_2026",
    }


# New columns appended to the 25-field master schema, in stable order.
MASTER_NEW_COLUMNS: tuple[str, ...] = (
    "india_priority", "ai_data_relevance", "fresher_potential",
    "url_confidence", "recommended_for_ai_data", "source",
)


def enrich_master_record(existing: dict[str, Any], row: MncRow, today: str) -> bool:
    """Blank-fill an existing master record from an Excel row. Returns changed?

    Never overwrites a non-empty existing value. Always stamps the new
    provenance columns (genuinely new signal) and records that the row was
    matched to the MNC master.
    """

    def is_blank(v: Any) -> bool:
        return v in (None, "", "Unknown", "unknown", [])

    changed = False
    candidate = master_record(row, today)
    # Blank-fill only the classic 25-field columns.
    for key, value in candidate.items():
        if key in MASTER_NEW_COLUMNS:
            continue
        if is_blank(existing.get(key)) and not is_blank(value):
            existing[key] = value
            changed = True
    # Provenance columns: always set (new signal, previously absent).
    existing["india_priority"] = row.priority
    existing["ai_data_relevance"] = row.relevance
    existing["fresher_potential"] = row.fresher
    existing["url_confidence"] = row.url_confidence
    existing["recommended_for_ai_data"] = "YES" if row.is_recommended else "Monitor"
    existing["source"] = _merge_source(existing.get("source"))
    return True if changed else True  # provenance stamp always counts as enriched


def _merge_source(current: Any) -> str:
    tokens = {t for t in str(current or "").split("+") if t and t != "None"}
    tokens.discard("")
    tokens.add("mnc_excel_2026")
    if not any(t.startswith("indian_seed") for t in tokens):
        tokens.add("indian_seed")
    return "+".join(sorted(tokens))
