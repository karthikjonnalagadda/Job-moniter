"""Normalization engine: freshness, salary, experience, employment, role, location."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.core.normalization.employment import EmploymentNormalizer
from app.core.normalization.experience import ExperienceNormalizer
from app.core.normalization.freshness import FreshnessParser
from app.core.normalization.location import LocationNormalizer
from app.core.normalization.roles import RoleNormalizer
from app.core.normalization.salary import SalaryNormalizer
from app.models.enums import EmploymentType, SeniorityLevel, WorkMode

_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
_TAX = Path("data/taxonomies")


# ---- freshness --------------------------------------------------------------
def _fresh() -> FreshnessParser:
    return FreshnessParser(now=lambda: _NOW)


@pytest.mark.parametrize(
    ("value", "expected_days_ago"),
    [("today", 0), ("yesterday", 1), ("2 days ago", 2), ("3 weeks ago", 21)],
)
def test_freshness_relative(value: str, expected_days_ago: int) -> None:
    parsed = _fresh().parse(value)
    assert parsed is not None
    assert round((_NOW - parsed).total_seconds() / 86400) == expected_days_ago


def test_freshness_iso_epoch_datetime_none() -> None:
    parser = _fresh()
    assert parser.parse("2026-01-02T00:00:00Z") == datetime(2026, 1, 2, tzinfo=UTC)
    assert parser.parse(1735732800).year == 2025  # unix seconds
    assert parser.parse(1735732800000).year == 2025  # unix millis
    assert parser.parse(datetime(2026, 1, 1)).tzinfo is UTC  # naive → aware
    assert parser.parse(None) is None
    assert parser.parse("garbage") is None


# ---- salary -----------------------------------------------------------------
def test_salary_lpa_range() -> None:
    s = SalaryNormalizer().parse("Compensation 25-35 LPA")
    assert s is not None
    assert (s.min_amount, s.max_amount) == (2500000.0, 3500000.0)
    assert (s.currency, s.period) == ("INR", "year")


def test_salary_usd_k_range_and_none() -> None:
    s = SalaryNormalizer().parse("$120k - $150k per year")
    assert s and (s.min_amount, s.max_amount, s.currency) == (120000.0, 150000.0, "USD")
    assert SalaryNormalizer().parse("competitive") is None  # no numbers
    assert SalaryNormalizer().parse("3+ years experience") is None  # no salary signal


def test_salary_crore_and_monthly() -> None:
    assert SalaryNormalizer().parse("1.2 crore CTC").min_amount == 12000000.0
    assert SalaryNormalizer().parse("stipend 25000 per month").period == "month"


# ---- experience -------------------------------------------------------------
def test_experience_variants() -> None:
    e = ExperienceNormalizer()
    assert e.parse("fresher").level == SeniorityLevel.FRESHER
    assert e.parse("entry level").max_years == 1.0
    assert (e.parse("2-4 years").min_years, e.parse("2-4 years").max_years) == (2.0, 4.0)
    assert e.parse("3+ years").min_years == 3.0
    assert e.parse("5 years experience").min_years == 5.0
    assert e.parse("").level == SeniorityLevel.UNKNOWN


# ---- employment -------------------------------------------------------------
def test_employment_types() -> None:
    e = EmploymentNormalizer()
    assert e.parse("Full time role") == EmploymentType.FULL_TIME
    assert e.parse("6-month internship") == EmploymentType.INTERNSHIP
    assert e.parse("Contract to hire") == EmploymentType.CONTRACT
    assert e.parse("Graduate program") == EmploymentType.GRADUATE_PROGRAM
    assert e.parse(None) == EmploymentType.UNKNOWN


# ---- roles ------------------------------------------------------------------
def test_role_normalization_taxonomy_and_fallback() -> None:
    roles = RoleNormalizer.from_file(_TAX / "roles.yaml")
    assert roles.normalize("Senior Machine Learning Engineer (NLP)") == "ML Engineer"
    assert roles.normalize("Backend Developer") == "Backend Engineer"
    # unknown title → cleaned fallback, never None for non-empty input
    assert roles.normalize("Chief Happiness Officer") is not None
    assert roles.normalize("") is None


# ---- location ---------------------------------------------------------------
def test_location_normalization() -> None:
    loc = LocationNormalizer.from_file(_TAX / "locations.yaml")
    bengaluru = loc.normalize("Bengaluru, India")
    assert bengaluru.city == "Bangalore"  # alias folded
    assert bengaluru.country == "IN"
    remote = loc.normalize("Remote (WFH)")
    assert remote.is_remote is True
    assert remote.work_mode == WorkMode.REMOTE
    assert "remote" in loc.tags(remote)
    assert loc.normalize("").city is None
