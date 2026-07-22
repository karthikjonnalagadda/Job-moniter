"""Quality score engine."""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.quality import QualityScorer
from app.models.common import Location
from app.models.job import Job


def _job(**kw: object) -> Job:
    base: dict[str, object] = {
        "job_hash": "h", "external_id": "1", "source": "greenhouse",
        "company_name": "Acme", "role": "Engineer", "url": "https://x/1",
    }
    base.update(kw)
    return Job(**base)  # type: ignore[arg-type]


def test_complete_job_scores_high() -> None:
    job = _job(
        description="Build things", location=Location(city="Bangalore"),
        posted_date=datetime(2026, 1, 1, tzinfo=UTC), skills=["Python"],
    )
    from app.models.common import SalaryRange

    job.salary = SalaryRange(min_amount=100.0)
    score = QualityScorer().score(job, parser=1.0, normalization=1.0)
    assert score.completeness == 1.0
    assert score.missing_fields == []
    assert score.overall > 0.95


def test_missing_fields_lower_completeness() -> None:
    job = _job()  # no description/location/posted/salary/skills
    score = QualityScorer().score(job)
    assert "description" in score.missing_fields
    assert "salary" in score.missing_fields
    assert score.completeness < 1.0


def test_duplicate_confidence_reduces_score() -> None:
    job = _job(description="x", skills=["Python"])
    clean = QualityScorer().score(job, duplicate_confidence=0.0)
    dup = QualityScorer().score(job, duplicate_confidence=0.9)
    assert dup.duplicate < clean.duplicate
    assert dup.overall < clean.overall
