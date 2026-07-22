"""Company validation engine — all required checks."""

from __future__ import annotations

from app.importers.validation import CompanyValidator, normalize_raw


def _rows(*records: dict) -> list[tuple[int, dict]]:
    return list(enumerate(records, start=1))


def test_normalize_aliases_and_strip() -> None:
    norm = normalize_raw({"Company": " Acme ", "ATS": "greenhouse", "Career URL": "https://x"})
    assert norm["name"] == "Acme"
    assert norm["ats_type"] == "greenhouse"
    assert norm["career_url"] == "https://x"


def test_valid_row_builds_company() -> None:
    valid, report = CompanyValidator().validate(
        _rows({"company": "Acme", "slug": "acme", "ats": "greenhouse", "career_url": "https://acme.example"})
    )
    assert report.is_valid
    assert len(valid) == 1
    assert valid[0][1].slug == "acme"


def test_missing_required_field() -> None:
    _, report = CompanyValidator().validate(_rows({"company": "NoSlug"}))
    assert not report.is_valid
    assert any(i.code == "missing_required_field" for i in report.errors)


def test_malformed_url_and_invalid_ats() -> None:
    _, report = CompanyValidator().validate(
        _rows({"company": "Bad", "slug": "bad", "career_url": "not-a-url", "ats": "notreal"})
    )
    codes = {i.code for i in report.errors}
    assert "malformed_url" in codes
    assert "invalid_ats_type" in codes


def test_duplicate_slug_url_and_token() -> None:
    _, report = CompanyValidator().validate(
        _rows(
            {"company": "A", "slug": "dup", "career_url": "https://x.example", "ats_token": "t1"},
            {"company": "B", "slug": "dup", "career_url": "https://x.example", "ats_token": "t1"},
        )
    )
    codes = {i.code for i in report.errors}
    assert {"duplicate_slug", "duplicate_career_url", "duplicate_board_token"} <= codes


def test_unsupported_country_when_restricted() -> None:
    validator = CompanyValidator(allowed_countries=frozenset({"US", "IN"}))
    _, report = validator.validate(
        _rows({"company": "Z", "slug": "z", "country": "ZZ"})
    )
    assert any(i.code == "unsupported_country" for i in report.errors)


def test_invalid_hiring_category_is_warning() -> None:
    valid, report = CompanyValidator().validate(
        _rows({"company": "A", "slug": "a", "hiring_category": "bogus"})
    )
    assert report.is_valid  # warning only, still imports
    assert any(i.code == "invalid_hiring_category" for i in report.warnings)
    assert len(valid) == 1
