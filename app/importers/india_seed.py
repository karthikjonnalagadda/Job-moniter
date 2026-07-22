"""Indian company career-site seed builder.

Turns the curated seed list (``Indian_Company_Career_Sites.md``) plus an
expanded metadata file into a single structured dataset, and emits it as CSV,
JSON, and YAML. The same records feed the MongoDB import through the existing
``CompanyImportService`` (so there is one validation/upsert path, not four).

Pipeline:

    seed table ─┐
                ├─▶ merge by slug ─▶ ATS auto-detect (fill gaps) ─▶ records
    metadata ───┘                                         │
                                                          ├─▶ CSV
                                                          ├─▶ JSON
                                                          └─▶ YAML  ─▶ Mongo

The builder never invents ATS tokens: detection only fills ``ats_type`` /
``ats_token`` / ``career_platform`` when the URL encodes them and the metadata
left them blank. Designed to scale to 10,000+ rows — records stream to CSV and
the structure is flat.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from app.config.logging import get_logger
from app.core.text import slugify
from app.importers.markdown_seed import parse_seed_table
from app.models.base import AppBaseModel
from app.models.enums import ATSType
from app.routing.detector import ATSDetector

log = get_logger("import")

# Canonical column order for the flat CSV/record shape.
FIELD_ORDER: tuple[str, ...] = (
    "name",
    "slug",
    "career_url",
    "career_platform",
    "industry",
    "headquarters",
    "country",
    "company_category",
    "ats_type",
    "ats_token",
    "priority_score",
    "ai_hiring_score",
    "remote_support",
    "active_status",
    "crawl_frequency",
    "supported_roles",
    "preferred_technologies",
    "aliases",
    "notes",
)

_LIST_FIELDS = ("supported_roles", "preferred_technologies", "aliases")
_DEFAULTS: dict[str, Any] = {
    "country": "IN",
    "company_category": "unknown",
    "ats_type": "unknown",
    "crawl_frequency": "weekly",
    "active_status": True,
    "priority_score": 50,
    "ai_hiring_score": 50,
    "remote_support": False,
}


class SeedStats(AppBaseModel):
    """Summary statistics for a generated dataset."""

    total: int
    from_seed_only: int  # rows present in the seed table but not the metadata
    from_metadata: int
    ats_detected: int  # rows whose ATS was auto-detected from the URL
    with_known_ats: int  # rows with any non-unknown ats_type
    remote_supported: int
    by_category: dict[str, int]
    by_ats: dict[str, int]


class IndiaSeedBuilder:
    """Builds and exports the Indian company career-site dataset."""

    def __init__(self, *, detector: ATSDetector | None = None) -> None:
        self._detector = detector or ATSDetector()
        self._detected = 0

    # ---- build ----------------------------------------------------------
    def build(self, seed_path: Path, metadata_path: Path | None = None) -> list[dict[str, Any]]:
        """Merge the seed table and metadata into enriched, de-duplicated records.

        De-duplication is by slug **and** by normalised career URL, so a company
        that appears in both the seed (simple slug) and the metadata (e.g. a
        legal-entity slug) collapses to one record instead of colliding on URL.
        """

        self._detected = 0
        by_slug: dict[str, dict[str, Any]] = {}
        seen_urls: dict[str, str] = {}  # normalised career URL -> owning slug

        for record in self._load_metadata(metadata_path):
            record.setdefault("slug", slugify(record.get("name", "")))
            slug = record["slug"]
            if not slug:
                continue
            url_key = self._norm_url(record.get("career_url"))
            if url_key and url_key in seen_urls:
                log.debug("Skipping '{}': duplicate career URL of '{}'", slug, seen_urls[url_key])
                continue
            by_slug[slug] = self._enrich(record, from_seed=False)
            if url_key:
                seen_urls[url_key] = slug

        for entry in parse_seed_table(seed_path):
            slug = slugify(entry.name)
            url_key = self._norm_url(entry.career_url)
            if slug in by_slug:
                if not by_slug[slug].get("career_url"):
                    by_slug[slug]["career_url"] = entry.career_url
                continue
            if url_key and url_key in seen_urls:
                continue  # already covered by a metadata record under another slug
            by_slug[slug] = self._enrich(
                {"name": entry.name, "slug": slug, "career_url": entry.career_url},
                from_seed=True,
            )
            if url_key:
                seen_urls[url_key] = slug

        records = [self._ordered(r) for r in by_slug.values()]
        records.sort(key=lambda r: (-float(r.get("priority_score") or 0), r["name"].lower()))
        log.info(
            "Built {} Indian company records ({} ATS auto-detected)",
            len(records),
            self._detected,
        )
        return records

    @staticmethod
    def _norm_url(url: Any) -> str:
        """Normalise a career URL for dedup (scheme/host/path, no trailing slash)."""

        if not url:
            return ""
        text = str(url).strip().lower()
        for prefix in ("https://", "http://"):
            if text.startswith(prefix):
                text = text[len(prefix) :]
        if text.startswith("www."):
            text = text[4:]
        return text.rstrip("/")

    def _load_metadata(self, path: Path | None) -> list[dict[str, Any]]:
        if path is None or not path.exists():
            log.info("No metadata file at {}; building from seed table only", path)
            return []
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        if isinstance(data, dict) and "companies" in data:
            data = data["companies"]
        if not isinstance(data, list):
            log.warning("Metadata file {} is not a list; ignoring", path)
            return []
        return [dict(item) for item in data if isinstance(item, dict)]

    def _enrich(self, record: dict[str, Any], *, from_seed: bool) -> dict[str, Any]:
        """Apply defaults and ATS auto-detection to a record in place."""

        out = dict(record)
        out["_from_seed"] = from_seed
        for field, default in _DEFAULTS.items():
            if out.get(field) in (None, ""):
                out[field] = default
        for field in _LIST_FIELDS:
            value = out.get(field)
            if value in (None, ""):
                out[field] = []
            elif not isinstance(value, list):
                out[field] = [str(value)]

        # Fill ATS wiring from the URL when metadata left it unknown.
        if str(out.get("ats_type", "unknown")).lower() == ATSType.UNKNOWN.value:
            detection = self._detector.detect(out.get("career_url"))
            if detection.detected:
                out["ats_type"] = detection.ats_type.value
                if detection.token and not out.get("ats_token"):
                    out["ats_token"] = detection.token
                if detection.platform and not out.get("career_platform"):
                    out["career_platform"] = detection.platform
                out["_ats_detected"] = True
                self._detected += 1
        return out

    @staticmethod
    def _ordered(record: dict[str, Any]) -> dict[str, Any]:
        ordered = {field: record.get(field) for field in FIELD_ORDER}
        # Preserve provenance flags used by stats (dropped before export).
        ordered["_from_seed"] = record.get("_from_seed", False)
        ordered["_ats_detected"] = record.get("_ats_detected", False)
        return ordered

    # ---- stats ----------------------------------------------------------
    def stats(self, records: list[dict[str, Any]]) -> SeedStats:
        by_category: Counter[str] = Counter()
        by_ats: Counter[str] = Counter()
        for record in records:
            by_category[str(record.get("company_category") or "unknown")] += 1
            by_ats[str(record.get("ats_type") or "unknown")] += 1
        return SeedStats(
            total=len(records),
            from_seed_only=sum(1 for r in records if r.get("_from_seed")),
            from_metadata=sum(1 for r in records if not r.get("_from_seed")),
            ats_detected=sum(1 for r in records if r.get("_ats_detected")),
            with_known_ats=sum(
                1 for r in records if str(r.get("ats_type")) != ATSType.UNKNOWN.value
            ),
            remote_supported=sum(1 for r in records if r.get("remote_support")),
            by_category=dict(sorted(by_category.items(), key=lambda kv: -kv[1])),
            by_ats=dict(sorted(by_ats.items(), key=lambda kv: -kv[1])),
        )

    # ---- export ---------------------------------------------------------
    def write_outputs(
        self, records: list[dict[str, Any]], out_dir: Path, *, basename: str = "indian_companies"
    ) -> dict[str, Path]:
        """Write CSV/JSON/YAML exports; return the paths keyed by format."""

        out_dir.mkdir(parents=True, exist_ok=True)
        clean = [self._export_row(r) for r in records]
        paths = {
            "csv": out_dir / f"{basename}.csv",
            "json": out_dir / f"{basename}.json",
            "yaml": out_dir / f"{basename}.yaml",
        }
        self._write_csv(clean, paths["csv"])
        paths["json"].write_text(
            json.dumps({"companies": clean}, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        paths["yaml"].write_text(
            yaml.safe_dump({"companies": clean}, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        log.info("Wrote {} records to {}", len(clean), out_dir)
        return paths

    @staticmethod
    def _export_row(record: dict[str, Any]) -> dict[str, Any]:
        return {field: record.get(field) for field in FIELD_ORDER}

    @staticmethod
    def _write_csv(records: list[dict[str, Any]], path: Path) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(FIELD_ORDER))
            writer.writeheader()
            for record in records:
                row = dict(record)
                for field in _LIST_FIELDS:
                    value = row.get(field) or []
                    row[field] = ";".join(value) if isinstance(value, list) else value
                writer.writerow(row)
