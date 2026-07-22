"""Filter chain: experience, freshness, location, role-relevance, seniority."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.filters.chain import FilterChain
from app.core.filters.experience import ExperienceFilter
from app.core.filters.freshness import FreshnessFilter
from app.core.filters.location import LocationFilter
from app.core.filters.role_relevance import RoleRelevanceFilter
from app.core.filters.seniority import SeniorityTitleFilter
from app.models.common import ExperienceRequirement, Location
from app.models.enums import SeniorityLevel
from app.models.job import Job

_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def _job(**kw: object) -> Job:
    base: dict[str, object] = {
        "job_hash": "h", "external_id": "1", "source": "greenhouse",
        "company_name": "Acme", "role": "Engineer", "url": "https://x/1",
    }
    base.update(kw)
    return Job(**base)  # type: ignore[arg-type]


def test_experience_filter() -> None:
    f = ExperienceFilter(max_years=2.0, allow_if_entry_level=True)
    assert f.check(_job(experience=ExperienceRequirement(min_years=1))).passed
    assert not f.check(_job(experience=ExperienceRequirement(min_years=5))).passed
    # entry-level override passes even with unknown/high years
    entry = _job(seniority=SeniorityLevel.FRESHER, experience=ExperienceRequirement(min_years=4))
    assert f.check(entry).passed
    # unknown experience is not discarded
    assert f.check(_job()).passed


def test_freshness_filter() -> None:
    f = FreshnessFilter(max_age_hours=24.0, now=lambda: _NOW)
    assert f.check(_job(posted_date=_NOW - timedelta(hours=5))).passed
    assert not f.check(_job(posted_date=_NOW - timedelta(hours=48))).passed
    assert f.check(_job(posted_date=None)).passed  # missing date passes


def test_location_filter() -> None:
    allow = LocationFilter(allowed=["Bangalore"], allow_remote=True)
    assert allow.check(_job(location=Location(city="Bangalore"))).passed
    assert not allow.check(_job(location=Location(city="Delhi"))).passed
    assert allow.check(_job(location=Location(is_remote=True))).passed  # remote allowed
    # no allow-list → pass-through
    assert LocationFilter().check(_job(location=Location(city="Anywhere"))).passed


def test_role_relevance_filter_accepts_target_roles() -> None:
    f = RoleRelevanceFilter()
    for role in [
        "AI Engineer", "Machine Learning Engineer", "Data Scientist", "Data Analyst",
        "Python Backend Engineer", "Software Engineer", "QA Automation Engineer",
        "SDET", "NLP Engineer", "Analytics Engineer", "Full Stack Developer",
    ]:
        assert f.check(_job(role=role)).passed, role


def test_role_relevance_filter_rejects_unrelated_roles() -> None:
    f = RoleRelevanceFilter()
    for role in [
        "HR Generalist", "Talent Acquisition Partner", "Sales Executive",
        "Account Executive", "Marketing Manager", "Financial Analyst",
        "Customer Success Manager", "Product Manager", "Benefits Specialist",
        "Graphic Designer", "Business Development Representative", "Legal Counsel",
    ]:
        assert not f.check(_job(role=role)).passed, role


def test_seniority_title_filter_rejects_senior_titles() -> None:
    f = SeniorityTitleFilter(max_years=2.0)
    for role in [
        "Senior Software Engineer", "Staff Data Scientist", "Lead ML Engineer",
        "Principal Engineer", "Engineering Manager", "Director of Engineering",
        "Solution Architect", "VP Engineering", "Head of Data", "CTO", "CIO",
        "Technical Lead", "Distinguished Engineer", "Vice President Engineering",
    ]:
        assert not f.check(_job(role=role)).passed, role
    # entry-level target roles pass
    assert f.check(_job(role="Data Scientist")).passed
    assert f.check(_job(role="Junior Backend Engineer")).passed
    assert f.check(_job(role="Associate Software Engineer")).passed
    # explicit senior/mid seniority enum is rejected regardless of title
    assert not f.check(_job(role="Engineer", seniority=SeniorityLevel.SENIOR)).passed
    assert not f.check(_job(role="Engineer", seniority=SeniorityLevel.MID)).passed
    # parsed years over budget is rejected
    assert not f.check(_job(role="Engineer", experience=ExperienceRequirement(min_years=6))).passed


def test_seniority_filter_rejects_level_markers_and_text_experience() -> None:
    f = SeniorityTitleFilter(max_years=2.0)
    # numeric / roman level markers (mid+ bands)
    for role in ["Software Engineer - II", "SDE-2", "Data Scientist III", "Backend Engineer L3",
                 "Data Scientist - MTS 2/3/4", "ML Engineer IC3", "AI Engineer 2/3"]:
        assert not f.check(_job(role=role)).passed, role
    # level 1 / entry is fine
    assert f.check(_job(role="SDE-1")).passed
    assert f.check(_job(role="Software Engineer I")).passed
    # experience parsed from description text
    assert not f.check(
        _job(role="Data Analyst", description="Minimum 4 years of experience.")
    ).passed
    assert not f.check(
        _job(role="ML Engineer", description="5+ years building ML systems.")
    ).passed
    # 0-2 / 2+ years are within budget
    assert f.check(
        _job(role="Data Analyst", description="0-2 years experience, freshers welcome.")
    ).passed
    # experienced-professional language, no entry signal → reject
    assert not f.check(
        _job(role="Backend Engineer", description="We seek a seasoned, experienced professional.")
    ).passed
    # same language but explicit entry signal in title → keep
    assert f.check(
        _job(role="Graduate Backend Engineer", description="experienced professional team")
    ).passed


def test_filter_chain_short_circuits_and_summarises() -> None:
    chain = FilterChain(
        [
            ExperienceFilter(max_years=2.0),
            FreshnessFilter(max_age_hours=24.0, now=lambda: _NOW),
        ]
    )
    jobs = [
        _job(experience=ExperienceRequirement(min_years=1), posted_date=_NOW),
        _job(experience=ExperienceRequirement(min_years=9)),  # rejected: experience
        _job(experience=ExperienceRequirement(min_years=1), posted_date=_NOW - timedelta(days=3)),
    ]
    kept, summary = chain.apply(jobs)
    assert len(kept) == 1
    assert summary.rejected == 2
    assert summary.rejected_by == {"experience": 1, "freshness": 1}
