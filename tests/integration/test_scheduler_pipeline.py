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
