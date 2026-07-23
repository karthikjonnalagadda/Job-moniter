"""Tests for the daily scheduler orchestration (app/scheduler/daily_pipeline).

Covers the new glue: work-list building, the idempotency guard, and an
end-to-end run with canned collection (no live ATS calls, no real email — the
test settings leave SMTP to_address empty so email is skipped).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from app.collectors.base import RawJob
from app.models.company import Company
from app.models.enums import ATSType, CompanyCategory, RunStatus
from app.models.run import SchedulerRun
from app.scheduler.daily_pipeline import (
    already_succeeded_today,
    build_work_list,
    resolve_resume_text,
    run_daily_pipeline,
)


def _company(slug: str, name: str, *, ats: ATSType = ATSType.GREENHOUSE) -> Company:
    return Company(
        name=name, slug=slug, ats_type=ats, ats_token="tok",
        company_category=CompanyCategory.SAAS,
    )


def _decision(slug: str, collector: str | None, routed: bool = True) -> SimpleNamespace:
    return SimpleNamespace(company_slug=slug, collector=collector, routed=routed)


class _StubRouter:
    def __init__(self, decisions: list[SimpleNamespace]) -> None:
        self._decisions = decisions

    def route_all(self, companies: list[Company]) -> SimpleNamespace:
        return SimpleNamespace(decisions=self._decisions)


# ---- pure glue --------------------------------------------------------------
def test_build_work_list_groups_by_collector() -> None:
    companies = [_company("acme", "Acme"), _company("beta", "Beta")]
    router = _StubRouter([_decision("acme", "greenhouse"), _decision("beta", "greenhouse")])
    work = build_work_list(companies, router)  # type: ignore[arg-type]
    assert len(work) == 1
    name, targets = work[0]
    assert name == "greenhouse"
    assert {t.company_slug for t in targets} == {"acme", "beta"}
    assert all(t.board_token == "tok" for t in targets)


def test_build_work_list_skips_unrouted_and_unknown() -> None:
    companies = [_company("acme", "Acme")]
    router = _StubRouter([
        _decision("acme", "greenhouse"),
        _decision("ghost", "lever"),               # no matching company
        _decision("acme", "lever", routed=False),  # not routed
        _decision("acme", None),                   # no collector
    ])
    work = dict(build_work_list(companies, router))  # type: ignore[arg-type]
    assert set(work) == {"greenhouse"}


def test_discover_collectors_registers_ats_collectors() -> None:
    # The scheduler routes to these ATS collectors; they must be discoverable.
    from app.collectors.loader import discover_collectors
    from app.collectors.registry import available_collectors

    discover_collectors()
    names = set(available_collectors())
    assert {"greenhouse", "lever", "ashby", "workday", "smartrecruiters"} <= names
    # "career_site" is the career-page ROUTING fallback name, not a real collector;
    # require_registered_collector=True makes such targets skip instead of crash.
    assert "career_site" not in names


def test_resolve_resume_text_prefers_env_then_file() -> None:
    from pathlib import Path

    env = SimpleNamespace(resume_text="ENV RESUME", paths=SimpleNamespace(resume_file=Path("nope")))
    assert resolve_resume_text(env) == "ENV RESUME"  # type: ignore[arg-type]


def test_resolve_resume_text_missing_is_empty_not_crash() -> None:
    from pathlib import Path

    missing = SimpleNamespace(resume_text="", paths=SimpleNamespace(resume_file=Path("nope")))
    assert resolve_resume_text(missing) == ""  # type: ignore[arg-type]


def test_smtp_settings_map_from_env(monkeypatch) -> None:
    from app.config.settings import Settings, get_settings

    for k, v in {
        "JOBAGENT_SMTP__HOST": "smtp.example.com",
        "JOBAGENT_SMTP__USERNAME": "sender@example.com",
        "JOBAGENT_SMTP__TO_ADDRESS": "recipient@example.com",
    }.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    s = Settings()
    assert s.smtp.host == "smtp.example.com"
    assert s.smtp.username == "sender@example.com"
    assert s.smtp.to_address == "recipient@example.com"


def test_already_succeeded_today() -> None:
    now = datetime.now(UTC)
    runs = [
        SchedulerRun(run_id="a", status=RunStatus.FAILED, started_at=now),
        SchedulerRun(run_id="b", status=RunStatus.SUCCESS, started_at=now - timedelta(days=1)),
    ]
    assert not already_succeeded_today(runs, now.date())
    runs.append(SchedulerRun(run_id="c", status=RunStatus.SUCCESS, started_at=now))
    assert already_succeeded_today(runs, now.date())


# ---- end-to-end (mock Mongo, canned collection) -----------------------------
@pytest.fixture
def scheduler_container(monkeypatch):
    from app.api.deps import build_container
    from app.config.settings import Settings, get_settings
    from app.db import mongo as mongo_module
    from mongomock_motor import AsyncMongoMockClient

    async def _connect(self) -> None:
        self._client = AsyncMongoMockClient()
        self._db = self._client[self._settings.mongo.db_name]

    monkeypatch.setattr(mongo_module.MongoClientManager, "connect", _connect)
    # Force SMTP fully neutral regardless of a developer's local .env, so the
    # default run skips email deterministically (matches CI, which has no .env).
    monkeypatch.setenv("JOBAGENT_SMTP__TO_ADDRESS", "")
    get_settings.cache_clear()
    return build_container(Settings())


async def test_run_daily_pipeline_end_to_end(scheduler_container, monkeypatch) -> None:
    from app.db.repositories.companies import CompanyRepository
    from app.db.repositories.runs import RunRepository

    container = scheduler_container
    await container.mongo.connect()
    db = container.mongo.db
    await CompanyRepository(db).upsert_by_slug(_company("acme", "Acme"))

    # Canned collection — no live ATS. Only .collector/.jobs/.errors are read.
    canned = SimpleNamespace(
        collector="greenhouse", errors=0,
        jobs=[RawJob(external_id="1", title="Data Analyst", company="Acme",
                     url="https://boards.greenhouse.io/acme/jobs/1",
                     description="0-2 years experience, freshers welcome")],
    )

    async def _run_many(self, work):
        return [canned]

    monkeypatch.setattr("app.collectors.executor.CollectorExecutor.run_many", _run_many)

    result = await run_daily_pipeline(container)

    assert result.status in (RunStatus.SUCCESS, RunStatus.PARTIAL)
    assert result.jobs_collected == 1
    assert result.email_sent is False  # no to_address configured -> email skipped
    persisted = await RunRepository(db).list_recent(limit=5)
    assert any(r.run_id == result.run_id for r in persisted)


async def test_run_daily_pipeline_delivers_email(scheduler_container, monkeypatch) -> None:
    from app.db.repositories.companies import CompanyRepository
    from app.notifications import smtp as smtp_module

    container = scheduler_container
    await container.mongo.connect()
    await CompanyRepository(container.mongo.db).upsert_by_slug(_company("acme", "Acme"))
    container.settings.smtp.to_address = "recipient@example.com"  # configure a recipient

    canned = SimpleNamespace(
        collector="greenhouse", errors=0,
        jobs=[RawJob(external_id="1", title="Data Analyst", company="Acme",
                     url="https://boards.greenhouse.io/acme/jobs/1",
                     description="0-2 years experience")],
    )

    async def _run_many(self, work):
        return [canned]

    sent: list[object] = []

    async def _send(self, message):  # fake a successful SMTP delivery
        sent.append(message)

    monkeypatch.setattr("app.collectors.executor.CollectorExecutor.run_many", _run_many)
    monkeypatch.setattr(smtp_module.SmtpNotifier, "send", _send)

    result = await run_daily_pipeline(container)

    assert result.status == RunStatus.SUCCESS
    assert result.excel_generated is True
    assert result.email_sent is True
    assert len(sent) == 1  # exactly one report email


async def test_scheduler_bootstraps_collectors(scheduler_container, monkeypatch) -> None:
    # The scheduler must discover/register collectors itself (the API does this in
    # create_app; the standalone run does not get that for free).
    import app.scheduler.daily_pipeline as dp
    from app.db.repositories.companies import CompanyRepository

    container = scheduler_container
    await container.mongo.connect()
    await CompanyRepository(container.mongo.db).upsert_by_slug(_company("acme", "Acme"))

    calls = {"n": 0}
    real = dp.discover_collectors

    def _spy():
        calls["n"] += 1
        return real()

    async def _run_many(self, work):
        return []

    monkeypatch.setattr(dp, "discover_collectors", _spy)
    monkeypatch.setattr("app.collectors.executor.CollectorExecutor.run_many", _run_many)

    await run_daily_pipeline(container)
    assert calls["n"] >= 1  # scheduler bootstrapped the collector registry


async def test_run_daily_pipeline_ranks_with_resume_env(scheduler_container, monkeypatch) -> None:
    from app.db.repositories.companies import CompanyRepository

    container = scheduler_container
    await container.mongo.connect()
    await CompanyRepository(container.mongo.db).upsert_by_slug(_company("acme", "Acme"))
    container.settings.resume_text = "Python developer, 1 year, SQL, pandas, FastAPI"

    canned = SimpleNamespace(
        collector="greenhouse", errors=0,
        jobs=[RawJob(external_id="1", title="Data Analyst", company="Acme",
                     url="https://boards.greenhouse.io/acme/jobs/1",
                     description="0-2 years, Python and SQL")],
    )

    async def _run_many(self, work):
        return [canned]

    monkeypatch.setattr("app.collectors.executor.CollectorExecutor.run_many", _run_many)

    result = await run_daily_pipeline(container)  # resume from env -> ranking path runs
    assert result.status in (RunStatus.SUCCESS, RunStatus.PARTIAL)
    assert result.jobs_collected == 1


async def test_routing_registers_ats_and_skips_career_site(scheduler_container) -> None:
    # The Issue-1 fix: after discovery + require_registered_collector=True, an ATS
    # company routes to its (registered) collector, and a career-only company
    # (routing target "career_site", which has no collector) is skipped, not crashed.
    from app.collectors.loader import discover_collectors
    from app.registry.loaders import YamlSourceLoader
    from app.routing.models import RoutingConfig
    from app.routing.router import CompanyRouter

    container = scheduler_container
    discover_collectors()
    await container.sources.load_from(
        YamlSourceLoader(container.settings.paths.ats_sources_file)
    )
    router = CompanyRouter(container.sources, RoutingConfig(require_registered_collector=True))

    gh_work = dict(build_work_list([_company("acme", "Acme", ats=ATSType.GREENHOUSE)], router))
    assert "greenhouse" in gh_work  # registered ATS collector -> routed

    career_only = Company(
        name="Careerco", slug="careerco", ats_type=ATSType.UNKNOWN,
        career_url="https://careerco.example/jobs",
    )
    assert build_work_list([career_only], router) == []  # career_site unregistered -> skipped


async def test_run_daily_pipeline_idempotent(scheduler_container, monkeypatch) -> None:
    from app.db.repositories.runs import RunRepository

    container = scheduler_container
    await container.mongo.connect()
    db = container.mongo.db
    await RunRepository(db).save(
        SchedulerRun(run_id="prev", status=RunStatus.SUCCESS, started_at=datetime.now(UTC))
    )

    called = {"n": 0}

    async def _run_many(self, work):
        called["n"] += 1
        return []

    monkeypatch.setattr("app.collectors.executor.CollectorExecutor.run_many", _run_many)

    result = await run_daily_pipeline(container)  # not forced
    assert result.status == RunStatus.SUCCESS
    assert "skipped" in " ".join(result.failures)
    assert called["n"] == 0  # idempotency prevented a duplicate execution


# ---- truthful status / observability (production-bug regression suite) ------
# A run that did NOT produce and deliver a report must never be recorded SUCCESS.

def _canned(collector: str = "greenhouse", *, errors: int = 0, ext: str = "1",
            url: str = "https://boards.greenhouse.io/acme/jobs/1") -> SimpleNamespace:
    return SimpleNamespace(
        collector=collector, errors=errors,
        jobs=[RawJob(external_id=ext, title="Data Analyst", company="Acme",
                     url=url, description="0-2 years experience, freshers welcome")],
    )


async def test_zero_jobs_generates_empty_report(scheduler_container, monkeypatch) -> None:
    # Case B: collectors ran clean but there were genuinely zero matching jobs.
    # This is a SUCCESS, but reporting is NOT skipped — an empty report is
    # generated and a "No matching jobs" email is sent.
    from app.db.repositories.companies import CompanyRepository
    from app.notifications import smtp as smtp_module

    container = scheduler_container
    await container.mongo.connect()
    await CompanyRepository(container.mongo.db).upsert_by_slug(_company("acme", "Acme"))
    container.settings.smtp.to_address = "recipient@example.com"

    async def _run_many(self, work):
        return []  # zero jobs, no collector errors

    sent: list[object] = []

    async def _send(self, message):
        sent.append(message)

    monkeypatch.setattr("app.collectors.executor.CollectorExecutor.run_many", _run_many)
    monkeypatch.setattr(smtp_module.SmtpNotifier, "send", _send)

    result = await run_daily_pipeline(container)
    assert result.jobs_collected == 0
    assert result.status == RunStatus.SUCCESS
    assert result.report_generated is True         # empty report WAS generated
    assert result.email_attempted is True
    assert result.email_sent is True               # and delivered
    assert result.delivery_status == "sent"
    assert len(sent) == 1
    assert "No matching jobs" in sent[0].subject   # email clearly states the empty result


async def test_zero_jobs_with_collector_errors_fails(scheduler_container, monkeypatch) -> None:
    # Zero jobs *because* collectors errored is a real failure, not a quiet day.
    from app.db.repositories.companies import CompanyRepository

    container = scheduler_container
    await container.mongo.connect()
    await CompanyRepository(container.mongo.db).upsert_by_slug(_company("acme", "Acme"))

    async def _run_many(self, work):
        return [SimpleNamespace(collector="greenhouse", errors=3, jobs=[])]

    monkeypatch.setattr("app.collectors.executor.CollectorExecutor.run_many", _run_many)

    result = await run_daily_pipeline(container)
    assert result.jobs_collected == 0
    assert result.status == RunStatus.FAILED
    assert any("no jobs collected" in f for f in result.failures)


async def test_report_generation_failure_fails_run(scheduler_container, monkeypatch) -> None:
    # If report generation throws, the run must FAIL (exit non-zero), not succeed.
    from app.db.repositories.companies import CompanyRepository
    from app.notifications.service import NotificationService

    container = scheduler_container
    await container.mongo.connect()
    await CompanyRepository(container.mongo.db).upsert_by_slug(_company("acme", "Acme"))
    container.settings.smtp.to_address = "recipient@example.com"

    async def _run_many(self, work):
        return [_canned()]

    async def _boom(self, **kwargs):
        raise RuntimeError("report backend exploded")

    monkeypatch.setattr("app.collectors.executor.CollectorExecutor.run_many", _run_many)
    monkeypatch.setattr(NotificationService, "send_report", _boom)

    result = await run_daily_pipeline(container)
    assert result.status == RunStatus.FAILED
    assert result.email_attempted is True   # we tried
    assert result.excel_generated is False
    assert result.email_sent is False
    assert any("RuntimeError" in f for f in result.failures)


async def test_email_delivery_failure_fails_run(scheduler_container, monkeypatch) -> None:
    # If the SMTP send throws, the run must FAIL and email_sent must stay False.
    from app.core.exceptions import NotificationError
    from app.db.repositories.companies import CompanyRepository
    from app.notifications import smtp as smtp_module

    container = scheduler_container
    await container.mongo.connect()
    await CompanyRepository(container.mongo.db).upsert_by_slug(_company("acme", "Acme"))
    container.settings.smtp.to_address = "recipient@example.com"

    async def _run_many(self, work):
        return [_canned()]

    async def _send_fail(self, message):
        raise NotificationError("smtp server refused the message")

    monkeypatch.setattr("app.collectors.executor.CollectorExecutor.run_many", _run_many)
    monkeypatch.setattr(smtp_module.SmtpNotifier, "send", _send_fail)

    result = await run_daily_pipeline(container)
    assert result.status == RunStatus.FAILED
    assert result.email_attempted is True
    assert result.email_sent is False
    assert result.failures  # a fatal failure was recorded


async def test_smtp_authentication_failure_fails_run(scheduler_container, monkeypatch) -> None:
    # An SMTP auth failure surfaces (via the notifier) as NotificationError; the
    # run must FAIL, not silently succeed.
    from app.core.exceptions import NotificationError
    from app.db.repositories.companies import CompanyRepository
    from app.notifications import smtp as smtp_module

    container = scheduler_container
    await container.mongo.connect()
    await CompanyRepository(container.mongo.db).upsert_by_slug(_company("acme", "Acme"))
    container.settings.smtp.to_address = "recipient@example.com"

    async def _run_many(self, work):
        return [_canned()]

    async def _auth_fail(self, message):
        raise NotificationError("Email delivery failed: 535 5.7.8 authentication failed")

    monkeypatch.setattr("app.collectors.executor.CollectorExecutor.run_many", _run_many)
    monkeypatch.setattr(smtp_module.SmtpNotifier, "send", _auth_fail)

    result = await run_daily_pipeline(container)
    assert result.status == RunStatus.FAILED
    assert result.email_attempted is True
    assert result.email_sent is False
    assert any("authentication failed" in f for f in result.failures)


async def test_partial_collector_failure_still_delivers(scheduler_container, monkeypatch) -> None:
    # One collector fails, another succeeds: jobs are still delivered. This is a
    # legitimate PARTIAL success (recorded, visible) — not a hard failure.
    from app.db.repositories.companies import CompanyRepository
    from app.notifications import smtp as smtp_module

    container = scheduler_container
    await container.mongo.connect()
    await CompanyRepository(container.mongo.db).upsert_by_slug(_company("acme", "Acme"))
    container.settings.smtp.to_address = "recipient@example.com"

    ok = _canned("greenhouse", errors=0, ext="1")
    bad = _canned("lever", errors=2, ext="2", url="https://jobs.lever.co/acme/2")

    async def _run_many(self, work):
        return [ok, bad]

    sent: list[object] = []

    async def _send(self, message):
        sent.append(message)

    monkeypatch.setattr("app.collectors.executor.CollectorExecutor.run_many", _run_many)
    monkeypatch.setattr(smtp_module.SmtpNotifier, "send", _send)

    result = await run_daily_pipeline(container)
    assert result.jobs_collected == 2
    assert result.collector_failures == 1
    assert result.status == RunStatus.PARTIAL      # a collector failed...
    assert result.report_generated is True         # ...but the report was still delivered
    assert result.email_sent is True
    assert result.excel_generated is True
    assert result.delivery_status == "sent"
    assert any("lever" in f and "error" in f for f in result.failures)
    assert len(sent) == 1


async def test_scheduler_run_records_all_fields(scheduler_container, monkeypatch) -> None:
    # A clean successful run must populate the full audit record honestly.
    from app.db.repositories.companies import CompanyRepository
    from app.notifications import smtp as smtp_module

    container = scheduler_container
    await container.mongo.connect()
    await CompanyRepository(container.mongo.db).upsert_by_slug(_company("acme", "Acme"))
    container.settings.smtp.to_address = "recipient@example.com"

    async def _run_many(self, work):
        return [_canned()]

    async def _send(self, message):
        return None

    monkeypatch.setattr("app.collectors.executor.CollectorExecutor.run_many", _run_many)
    monkeypatch.setattr(smtp_module.SmtpNotifier, "send", _send)

    r = await run_daily_pipeline(container)
    assert r.status == RunStatus.SUCCESS
    assert r.jobs_collected == 1
    assert r.ai_ranked >= 0            # jobs_ranked
    assert r.collector_failures == 0
    assert r.report_generated is True
    assert r.excel_generated is True
    assert r.email_attempted is True
    assert r.email_sent is True
    assert r.delivery_status == "sent"
    assert r.duration_seconds is not None   # execution_time recorded


async def test_production_missing_recipient_fails(monkeypatch) -> None:
    # In production, jobs collected but no recipient configured => FAILED, not a
    # silent green run. (This is the exact production incident.)
    from app.api.deps import build_container
    from app.config.settings import Settings, get_settings
    from app.db import mongo as mongo_module
    from app.db.repositories.companies import CompanyRepository
    from mongomock_motor import AsyncMongoMockClient

    async def _connect(self) -> None:
        self._client = AsyncMongoMockClient()
        self._db = self._client[self._settings.mongo.db_name]

    monkeypatch.setattr(mongo_module.MongoClientManager, "connect", _connect)
    monkeypatch.setenv("JOBAGENT_ENV", "production")
    monkeypatch.setenv("JOBAGENT_MONGO__URI", "mongodb://real.invalid:27017")  # pass prod validator
    monkeypatch.setenv("JOBAGENT_SMTP__TO_ADDRESS", "")  # no recipient
    get_settings.cache_clear()
    try:
        container = build_container(Settings())
        await container.mongo.connect()
        await CompanyRepository(container.mongo.db).upsert_by_slug(_company("acme", "Acme"))

        async def _run_many(self, work):
            return [_canned()]

        monkeypatch.setattr("app.collectors.executor.CollectorExecutor.run_many", _run_many)

        result = await run_daily_pipeline(container)
        assert result.jobs_collected == 1
        assert result.status == RunStatus.FAILED
        assert any("to_address" in f for f in result.failures)
    finally:
        get_settings.cache_clear()


async def test_run_daily_exit_code_reflects_status(monkeypatch) -> None:
    # The CLI must exit non-zero on a FAILED run and zero otherwise, so GitHub
    # Actions marks the job failed when the pipeline did not truthfully complete.
    import app.scheduler.run_daily as rd
    from app.config.settings import get_settings
    from app.db import mongo as mongo_module

    async def _noop(self) -> None:
        return None

    async def _ping_ok(self) -> bool:
        return True

    monkeypatch.setattr(mongo_module.MongoClientManager, "connect", _noop)
    monkeypatch.setattr(mongo_module.MongoClientManager, "disconnect", _noop)
    monkeypatch.setattr(mongo_module.MongoClientManager, "ping", _ping_ok)
    get_settings.cache_clear()

    async def _failed(container, *, force=False):
        return SchedulerRun(run_id="x", status=RunStatus.FAILED)

    monkeypatch.setattr(rd, "run_daily_pipeline", _failed)
    assert await rd._run() == 1  # FAILED -> non-zero

    async def _ok(container, *, force=False):
        return SchedulerRun(run_id="y", status=RunStatus.SUCCESS)

    monkeypatch.setattr(rd, "run_daily_pipeline", _ok)
    assert await rd._run() == 0  # SUCCESS -> zero
