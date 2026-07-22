"""Retry queue service + raw payload archive."""

from __future__ import annotations

from datetime import datetime

import httpx
from app.collectors.archive import RawArchiver
from app.collectors.retry_queue import RetryQueue
from app.db.repositories.raw_payloads import RawPayloadRepository
from app.db.repositories.retry_queue import RetryQueueRepository
from app.models.retry_task import RetryStatus

# Naive UTC: mongomock strips tzinfo on read, so keep the injected clock naive
# to make round-tripped datetime comparisons stable in tests.
_NOW = datetime(2026, 1, 1, 12, 0)


async def test_retry_backoff_and_due(mock_db) -> None:
    repo = RetryQueueRepository(mock_db)
    queue = RetryQueue(repo, now=lambda: _NOW)

    task = await queue.enqueue_failure("greenhouse", {"board_token": "acme"}, error="boom")
    assert task.attempts == 1
    assert task.status == RetryStatus.PENDING
    assert task.backoff_seconds == 30.0  # base backoff for attempt 0
    assert task.next_attempt_at == _NOW.replace(minute=0, second=30)

    # not due yet (future); becomes due once the clock passes next_attempt_at
    assert await queue.due_tasks() == []
    later = RetryQueue(repo, now=lambda: _NOW.replace(hour=13))
    due = await later.due_tasks()
    assert len(due) == 1 and due[0].collector == "greenhouse"


async def test_retry_exhaustion(mock_db) -> None:
    queue = RetryQueue(RetryQueueRepository(mock_db), now=lambda: _NOW)
    task = await queue.enqueue_failure(
        "lever", {"board_token": "x"}, error="boom", attempts=5, max_attempts=5
    )
    assert task.status == RetryStatus.EXHAUSTED
    assert task.next_attempt_at is None


async def test_raw_archiver_disabled_is_noop(mock_db) -> None:
    repo = RawPayloadRepository(mock_db)
    archiver = RawArchiver(repo, enabled=False)
    assert archiver.enabled is False
    await archiver.archive(
        collector="greenhouse", url="https://x", response=httpx.Response(200, json={})
    )
    assert await repo.count() == 0


async def test_raw_archiver_stores_payload(mock_db) -> None:
    repo = RawPayloadRepository(mock_db)
    archiver = RawArchiver(repo, enabled=True)
    response = httpx.Response(200, json={"jobs": []}, headers={"etag": "v9"})
    await archiver.archive(
        collector="greenhouse", url="https://x/jobs", response=response, source_slug="acme"
    )
    stored = await repo.latest_for("greenhouse")
    assert len(stored) == 1
    assert stored[0].etag == "v9"
    assert stored[0].source_slug == "acme"
