"""Validation/coercion of the Phase-5 company fields (categories, lists, freq)."""

from __future__ import annotations

from app.importers.validation import CompanyValidator, normalize_raw
from app.models.enums import CompanyCategory, CrawlFrequency


def test_normalize_splits_delimited_lists() -> None:
    norm = normalize_raw(
        {
            "Company": "Acme",
            "slug": "acme",
            "supported_roles": "Engineer; Data Scientist ;PM",
            "preferred_technologies": "Python|Go",
            "aliases": "Acme Corp; ACME",
        }
    )
    assert norm["supported_roles"] == ["Engineer", "Data Scientist", "PM"]
    assert norm["preferred_technologies"] == ["Python", "Go"]
    assert norm["aliases"] == ["Acme Corp", "ACME"]


def test_valid_new_fields_build_company() -> None:
    rows = [
        (
            1,
            {
                "name": "Acme",
                "slug": "acme",
                "company_category": "fintech",
                "crawl_frequency": "daily",
                "priority_score": "80",
                "supported_roles": ["SWE"],
            },
        )
    ]
    valid, report = CompanyValidator().validate(rows)
    assert report.invalid_rows == 0
    company = valid[0][1]
    assert company.company_category == CompanyCategory.FINTECH
    assert company.crawl_frequency == CrawlFrequency.DAILY
    assert company.priority_score == 80.0
    assert company.supported_roles == ["SWE"]


def test_unknown_category_and_frequency_warn_and_default() -> None:
    rows = [
        (
            1,
            {
                "name": "Acme",
                "slug": "acme",
                "company_category": "spaceship",
                "crawl_frequency": "hourly",
            },
        )
    ]
    valid, report = CompanyValidator().validate(rows)
    assert report.invalid_rows == 0  # warnings, not errors
    codes = {i.code for i in report.issues}
    assert "invalid_company_category" in codes
    assert "invalid_crawl_frequency" in codes
    company = valid[0][1]
    assert company.company_category == CompanyCategory.UNKNOWN
    assert company.crawl_frequency == CrawlFrequency.WEEKLY  # model default
