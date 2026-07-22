"""Retry-queue service.

Persists failed collector fetches with deterministic exponential-backoff
scheduling (no jitter, so ``next_attempt_at`` is predictable), and replays due
tasks. Time is injected for testability.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from app.config.logging import get_logger
from app.models.retry_task import RetryStatus, RetryTask

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.db.repositories.retry_queue import RetryQueueRepository

log = get_logger("collectors")

_BASE_SECONDS = 30.0
_MAX_SECONDS = 3600.0


def _backoff_seconds(attempts: int) -> float:
    return min(_MAX_SECONDS, _BASE_SECONDS * (2**attempts))


class RetryQueue:
    """Enqueue failed fetches and replay them on an exponential backoff."""

    def __init__(
        self,
        repo: RetryQueueRepository,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        self._repo = repo
        self._now = now

    async def enqueue_failure(
        self,
        collector: str,
        target: dict[str, Any],
        *,
        error: str,
        task_id: str | None = None,
        attempts: int = 0,
        max_attempts: int = 5,
    ) -> RetryTask:
        """Record a failed fetch, scheduling its next attempt with backoff."""

        next_attempts = attempts + 1
        if next_attempts > max_attempts:
            status = RetryStatus.EXHAUSTED
            delay = 0.0
            next_at = None
        else:
            status = RetryStatus.PENDING
            delay = _backoff_seconds(attempts)
            next_at = self._now() + timedelta(seconds=delay)

        task = RetryTask(
            task_id=task_id or uuid.uuid4().hex,
            collector=collector,
            target=target,
            attempts=next_attempts,
            max_attempts=max_attempts,
            backoff_seconds=delay,
            next_attempt_at=next_at,
            last_error=error,
            status=status,
        )
        saved = await self._repo.upsert_task(task)
        log.warning(
            "Retry queued: {} attempt {}/{} in {}s ({})",
            collector,
            next_attempts,
            max_attempts,
            delay,
            status,
        )
        return saved

    async def due_tasks(self, *, limit: int = 50) -> list[RetryTask]:
        return await self._repo.due(now=self._now(), limit=limit)

    async def mark_done(self, task_id: str) -> None:
        await self._repo.set_status(task_id, RetryStatus.DONE)
