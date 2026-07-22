"""CollectorExecutor: run isolation, benchmarks, state, retry, archive."""

from __future__ import annotations

import httpx
from app.collectors.archive import RawArchiver
from app.collectors.base import CollectorTarget
from app.collectors.context import CollectorContext
from app.collectors.executor import CollectorExecutor
from app.collectors.retry_queue import RetryQueue
from app.collectors.state import CollectorState, CollectorStateRegistry
from app.config.settings import Settings
from app.db.repositories.benchmarks import BenchmarkRepository
from app.db.repositories.raw_payloads import RawPayloadRepository
from app.db.repositories.retry_queue import RetryQueueRepository
from app.pipeline.stages import CollectStage

from tests.http_fakes import GREENHOUSE_JOBS, FakeHttpClient

TARGET = CollectorTarget(board_token="acme", company_name="Acme")


def _context(mock_db, handler) -> CollectorContext:
    return CollectorContext(
        http=FakeHttpClient(handler),
        settings=Settings(),
        archive=RawArchiver(RawPayloadRepository(mock_db), enabled=True),
        benchmarks=BenchmarkRepository(mock_db),
        states=CollectorStateRegistry(),
        retry_queue=RetryQueue(RetryQueueRepository(mock_db)),
    )


async def test_successful_run_records_benchmark_and_archives(mock_db) -> None:
    def handler(method, url, **_):
        return httpx.Response(200, json=GREENHOUSE_JOBS, headers={"etag": "v1"})

    ctx = _context(mock_db, handler)
    result = await CollectorExecutor(ctx).run("greenhouse", [TARGET])

    assert result.ok is True
    assert result.jobs_found == 1
    assert result.state == CollectorState.IDLE
    assert result.sync["etag"] == "v1"

    # benchmark recorded
    benchmark = await BenchmarkRepository(mock_db).get_for("greenhouse")
    assert benchmark is not None and benchmark.runs == 1 and benchmark.total_jobs_found == 1
    # raw payload archived
    assert len(await RawPayloadRepository(mock_db).latest_for("greenhouse")) == 1


async def test_failure_is_isolated_and_enqueues_retry(mock_db) -> None:
    def handler(method, url, **_):
        return httpx.Response(500)  # Greenhouse collector raises CollectorError

    ctx = _context(mock_db, handler)
    result = await CollectorExecutor(ctx).run("greenhouse", [TARGET])

    assert result.ok is False
    assert result.errors == 1
    assert result.state == CollectorState.FAILED
    # a retry task was persisted
    assert await RetryQueueRepository(mock_db).count_pending() == 1


async def test_run_many_isolates_collectors(mock_db) -> None:
    def handler(method, url, **_):
        if "lever" in url:
            return httpx.Response(500)  # lever fails
        return httpx.Response(200, json=GREENHOUSE_JOBS, headers={"etag": "v1"})

    ctx = _context(mock_db, handler)
    results = await CollectorExecutor(ctx).run_many(
        [("greenhouse", [TARGET]), ("lever", [TARGET])]
    )
    by_name = {r.collector: r for r in results}
    assert by_name["greenhouse"].ok is True  # unaffected by lever's failure
    assert by_name["lever"].ok is False


async def test_collect_stage_returns_jobs(mock_db) -> None:
    def handler(method, url, **_):
        return httpx.Response(200, json=GREENHOUSE_JOBS, headers={"etag": "v1"})

    stage = CollectStage(CollectorExecutor(_context(mock_db, handler)))
    jobs = await stage.run([("greenhouse", [TARGET])])
    assert len(jobs) == 1
    assert jobs[0].external_id == "123"
