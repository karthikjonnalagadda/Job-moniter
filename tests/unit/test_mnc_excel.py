"""MNC Excel importer — validation tests (requirement 12).

Confirms: Excel import works; existing companies stay intact; new companies are
inserted; duplicates are not created (name/alias/domain); career URLs are
normalised; ATS detection works (incl. no substring false positives); and the
role filter now recognises "Applied Scientist" while still dropping senior roles.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core.filters.role_relevance import RoleRelevanceFilter
from app.core.filters.seniority import SeniorityTitleFilter
from app.importers.aliases import AliasResolver
from app.importers.mnc_excel import (
    MASTER_NEW_COLUMNS,
    MncExcelReader,
    normalize_name,
    normalize_url,
    registrable_domain,
)
from app.importers.mnc_merge import merge_master, merge_runtime
from app.models.job import Job
from app.routing.detector import ATSDetector

_TODAY = "2026-08-09"


# ---- URL normalisation ---------------------------------------------------
def test_normalize_url_strips_tracking_and_fragment() -> None:
    got = normalize_url("HTTPS://Careers.Example.com/jobs?utm_source=x&ref=y&team=ai#frag")
    assert got == "https://careers.example.com/jobs?team=ai"


def test_normalize_url_rejects_malformed() -> None:
    assert normalize_url("not a url") == ""
    assert normalize_url("ftp://example.com") == ""
    assert normalize_url("javascript:alert(1)") == ""


def test_registrable_domain_handles_two_level_tlds() -> None:
    assert registrable_domain("https://www.bmwgroup.jobs/") == "bmwgroup.jobs"
    assert registrable_domain("https://careers.tesco.co.uk/jobs") == "tesco.co.uk"


# ---- Name normalisation / dedup equivalence ------------------------------
def test_normalize_name_ignores_legal_suffixes() -> None:
    assert normalize_name("Unilever") == normalize_name("Unilever Ltd")
    assert normalize_name("Acme Technologies India") == normalize_name("Acme")


# ---- ATS detection (incl. false-positive guard) --------------------------
def test_ats_detection_no_substring_false_positive() -> None:
    det = ATSDetector()
    assert det.detect("https://www.hindustanunilever.com/careers").detected is False
    assert det.detect("https://jobs.lever.co/acme").ats_type.value == "lever"


# ---- Excel reader --------------------------------------------------------
def _write_xlsx(path: Path, rows: list[tuple[str, ...]]) -> None:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MNC Career Sites"
    ws.append(
        [
            "S.No.", "Company", "Sector", "HQ", "India Opportunity Priority",
            "AI/ML & Data Relevance", "Fresher / 0-2 YOE Potential",
            "Official Careers URL", "URL Confidence", "India Search Keywords",
            "Notes", "Recommended for AI/Data Profile",
        ]
    )
    for i, r in enumerate(rows, start=1):
        ws.append([i, *r])
    wb.save(path)


@pytest.fixture
def sample_xlsx(tmp_path: Path) -> Path:
    path = tmp_path / "mnc.xlsx"
    _write_xlsx(
        path,
        [
            ("Acme Global", "Big Tech & Product", "USA", "Tier 1", "High", "Strong",
             "https://boards.greenhouse.io/acme?utm_source=x", "High",
             "Acme India AI ML", "note", "YES"),
            ("Google LLC", "Big Tech & Product", "USA", "Tier 1", "High", "Strong",
             "https://careers.google.com/", "Verify", "Google India jobs", "", "Monitor"),
        ],
    )
    return path


def test_reader_parses_and_maps(sample_xlsx: Path) -> None:
    rows = MncExcelReader().read(sample_xlsx)
    assert len(rows) == 2
    acme = rows[0]
    assert acme.company == "Acme Global"
    assert acme.url == "https://boards.greenhouse.io/acme"  # tracking stripped
    assert acme.detection.ats_type.value == "greenhouse"
    assert acme.detection.token == "acme"
    assert acme.url_verified is True


# ---- Merge: dedup, new insert, enrich, integrity -------------------------
def test_merge_master_dedups_and_appends(sample_xlsx: Path) -> None:
    rows = MncExcelReader().read(sample_xlsx)
    resolver = AliasResolver.from_file(Path("data/company_aliases.yaml"))
    # Existing master already has Google (as "Google") — Google LLC must match it
    # via the alias map, not create a duplicate.
    master = [
        {"company_name": "Google", "career_url": "https://www.google.com/about/careers/",
         "website": "", "industry": "", "category": "product", "ats_platform": "Unknown",
         "ats_token": "Unknown"},
    ]
    before = len(master)
    new_records, enriched, matched = merge_master(master, rows, resolver, _TODAY)

    assert matched == 1                       # Google LLC matched existing Google
    assert enriched == 1
    assert len(new_records) == 1              # only Acme Global is new
    assert new_records[0]["company_name"] == "Acme Global"
    assert len(master) == before              # existing list not grown in place
    # Existing Google record enriched (blank industry filled), provenance stamped.
    assert master[0]["industry"] == "Big Tech & Product"
    assert master[0]["source"].startswith("indian_seed") or "mnc_excel_2026" in master[0]["source"]


def test_merge_master_enrich_is_blank_fill_only(sample_xlsx: Path) -> None:
    rows = MncExcelReader().read(sample_xlsx)
    resolver = AliasResolver.from_file(Path("data/company_aliases.yaml"))
    master = [
        {"company_name": "Google", "industry": "Search & Ads (existing)",
         "career_url": "https://www.google.com/about/careers/", "ats_platform": "Unknown"},
    ]
    merge_master(master, rows, resolver, _TODAY)
    # Pre-existing non-empty value is preserved, never overwritten.
    assert master[0]["industry"] == "Search & Ads (existing)"


def test_new_master_record_has_all_new_columns(sample_xlsx: Path) -> None:
    rows = MncExcelReader().read(sample_xlsx)
    resolver = AliasResolver.from_file(Path("data/company_aliases.yaml"))
    new_records, _, _ = merge_master([], rows, resolver, _TODAY)
    for rec in new_records:
        for col in MASTER_NEW_COLUMNS:
            assert col in rec
        assert rec["source"] == "mnc_excel_2026"


def test_merge_master_dedups_new_vs_new_by_domain(tmp_path: Path) -> None:
    # The Excel lists one company twice (ADM == Archer Daniels Midland, same
    # domain). Only ONE new record must be created, not two.
    path = tmp_path / "dupe.xlsx"
    _write_xlsx(
        path,
        [
            ("ADM", "Food, Agriculture & Chemicals", "USA", "Tier 2", "Medium",
             "Possible", "https://www.adm.com/careers/", "Verify", "", "", "Monitor"),
            ("Archer Daniels Midland", "Food, Agriculture & Chemicals", "USA", "Tier 2",
             "Medium", "Possible", "https://www.adm.com/en-us/careers/", "Verify",
             "", "", "Monitor"),
        ],
    )
    rows = MncExcelReader().read(path)
    resolver = AliasResolver.from_file(Path("data/company_aliases.yaml"))
    new_records, _, matched = merge_master([], rows, resolver, _TODAY)
    assert len(new_records) == 1
    assert matched == 1  # the second spelling counts as a duplicate


def test_merge_runtime_skips_existing(sample_xlsx: Path) -> None:
    rows = MncExcelReader().read(sample_xlsx)
    resolver = AliasResolver.from_file(Path("data/company_aliases.yaml"))
    runtime = [{"name": "Google", "aliases": ["Google LLC"], "career_url": ""}]
    additions = merge_runtime(runtime, rows, resolver)
    names = {r["name"] for r in additions}
    assert "Google LLC" not in names          # already a first-class runtime seed
    assert "Acme Global" in names             # genuinely new


# ---- Role filtering still correct (requirement 8) ------------------------
def _job(**kw: object) -> Job:
    base: dict[str, object] = {
        "job_hash": "h", "external_id": "1", "source": "greenhouse",
        "company_name": "Acme", "role": "Engineer", "url": "https://x/1",
    }
    base.update(kw)
    return Job(**base)  # type: ignore[arg-type]


def test_role_filter_accepts_applied_scientist() -> None:
    f = RoleRelevanceFilter()
    assert f.check(_job(role="Applied Scientist")).passed
    assert f.check(_job(role="Applied Scientist II")).passed


def test_seniority_filter_still_rejects_senior_roles() -> None:
    f = SeniorityTitleFilter(max_years=2.0)
    for role in ("Senior Data Scientist", "Staff ML Engineer", "Principal Engineer",
                 "Engineering Manager", "Lead Data Engineer"):
        assert not f.check(_job(role=role)).passed, role
