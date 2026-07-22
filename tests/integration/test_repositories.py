"""Repository CRUD against an in-memory Mongo (mongomock-motor)."""

from __future__ import annotations

from app.db.repositories.companies import CompanyRepository
from app.db.repositories.jobs import JobRepository
from app.db.repositories.runs import RunRepository
from app.db.repositories.user_preferences import UserPreferencesRepository
from app.db.repositories.users import UserRepository
from app.models.company import Company
from app.models.enums import ATSType, JobStatus, RunStatus
from app.models.job import Job, MatchDetail
from app.models.run import SchedulerRun
from app.models.user_preferences import ResumeVersion


async def test_job_insert_get_and_dedup_upsert(mock_db) -> None:
    repo = JobRepository(mock_db)
    job = Job(
        job_hash="h1",
        external_id="e1",
        source="greenhouse",
        company_name="Acme",
        role="Engineer",
        url="http://x",
    )

    inserted = await repo.insert(job)
    assert inserted.id is not None
    assert inserted.created_at is not None

    fetched = await repo.get(inserted.id)
    assert fetched is not None and fetched.job_hash == "h1"

    # upsert on the same hash updates in place (no duplicate)
    job.role = "Senior Engineer"
    await repo.upsert_by_hash(job)
    assert await repo.count() == 1
    assert await repo.exists_hash("h1") is True


async def test_job_status_and_ranked_listing(mock_db) -> None:
    repo = JobRepository(mock_db)
    j = Job(
        job_hash="h2",
        external_id="e2",
        source="greenhouse",
        company_name="Acme",
        role="Dev",
        url="http://y",
    )
    j.match = MatchDetail(score=88)
    await repo.upsert_by_hash(j)

    await repo.set_status("h2", JobStatus.REPORTED)
    top = await repo.list_top_ranked(min_score=50)
    assert top and top[0].match is not None and top[0].match.score == 88


async def test_company_slug_upsert(mock_db) -> None:
    repo = CompanyRepository(mock_db)
    await repo.upsert_by_slug(Company(name="Acme", slug="acme", ats_type=ATSType.GREENHOUSE))
    await repo.upsert_by_slug(Company(name="Acme Inc", slug="acme", ats_type=ATSType.GREENHOUSE))
    assert await repo.count() == 1
    found = await repo.get_by_slug("acme")
    assert found is not None and found.name == "Acme Inc"

    by_ats = await repo.list_by_ats(ATSType.GREENHOUSE)
    assert len(by_ats) == 1


async def test_user_default_and_preferences_resume_versioning(mock_db) -> None:
    users = UserRepository(mock_db)
    user = await users.ensure_default(email="owner@example.com")
    assert user.user_id == "default"
    # idempotent
    again = await users.ensure_default(email="owner@example.com")
    assert again.user_id == "default"
    assert await users.count() == 1

    prefs = UserPreferencesRepository(mock_db)
    await prefs.add_resume_version(
        ResumeVersion(version_id="backend", label="Backend Resume", embedding=[0.1] * 384),
        make_active=True,
    )
    loaded = await prefs.get_for_user()
    assert loaded is not None
    assert loaded.active_resume_id == "backend"
    assert loaded.resume_embedding == [0.1] * 384
    assert loaded.active_resume() is not None


async def test_run_history_upsert(mock_db) -> None:
    repo = RunRepository(mock_db)
    await repo.save(SchedulerRun(run_id="run_1", status=RunStatus.RUNNING, jobs_collected=10))
    await repo.save(SchedulerRun(run_id="run_1", status=RunStatus.SUCCESS, jobs_collected=12))
    assert await repo.count() == 1
    run = await repo.get_by_run_id("run_1")
    assert run is not None and run.status == "success" and run.jobs_collected == 12
