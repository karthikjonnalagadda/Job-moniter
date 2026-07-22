"""Analytics service aggregations (mongomock-backed)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.analytics.service import AnalyticsService
from app.db.repositories.jobs import JobRepository
from app.db.repositories.pipeline_runs import PipelineRunRepository
from app.models.common import Location, SalaryRange
from app.models.job import Job, MatchDetail
from app.models.pipeline_run import PipelineRun, StageStat


async def _seed(db) -> JobRepository:  # type: ignore[no-untyped-def]
    repo = JobRepository(db)
    specs = [
        ("Google", "ML Engineer", 90, "ai"),
        ("Alphabet", "ML Engineer", 80, "ai"),
        ("Flipkart", "Backend Engineer", 60, "backend"),
    ]
    for i, (company, role, score, resume) in enumerate(specs):
        await repo.upsert_by_hash(
            Job(
                job_hash=f"h{i}", external_id=str(i), source="greenhouse", company_name=company,
                canonical_company_name="Alphabet" if company in {"Google", "Alphabet"} else company,
                role=role, normalized_role=role, url=f"https://x/{i}",
                location=Location(city="Bangalore", country="IN"),
                salary=SalaryRange(
                    min_amount=2_000_000, max_amount=3_000_000, currency="INR", period="year"
                ),
                skills=["Python", "FastAPI"], technologies=["Python"],
                posted_date=datetime(2026, 7, 21, tzinfo=UTC),
                match=MatchDetail(score=score, resume_id=resume, missing_skills=["Docker"]),
            )
        )
    return repo


async def test_analytics_aggregations(mock_db) -> None:
    repo = await _seed(mock_db)
    report = await AnalyticsService(repo).build()
    assert report.total_jobs == 3
    assert report.ranked_jobs == 3
    assert 60 <= report.average_match <= 90
    # canonical company folding: Google+Alphabet count as Alphabet
    top_company = report.companies[0]
    assert top_company.label == "Alphabet" and top_company.count == 2
    assert any(r.label == "ML Engineer" and r.count == 2 for r in report.roles)
    assert report.salaries[0].currency == "INR"
    # match trends split by resume version
    resumes = {t.resume_id for t in report.match_trends}
    assert resumes == {"ai", "backend"}


async def test_pipeline_performance(mock_db) -> None:
    repo = JobRepository(mock_db)
    runs = PipelineRunRepository(mock_db)
    await runs.insert(
        PipelineRun(
            run_id="r1", collected=100, stored=40, duplicates=10, filtered_out=50,
            duration_seconds=2.0, started_at=datetime(2026, 7, 21, tzinfo=UTC),
            stages=[StageStat(name="normalize", count_in=100, count_out=100, duration_ms=500.0)],
        )
    )
    perf = await AnalyticsService(repo, runs=runs).pipeline_performance()
    assert perf.total_runs == 1
    assert perf.total_collected == 100
    assert perf.avg_stage_ms["normalize"] == 500.0
