"""Retry-task model.

A failed collector fetch is persisted here (instead of retried immediately) with
exponential-backoff metadata so it can be replayed safely later. Stored in
``retry_queue``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from app.models.base import MongoDocument


class RetryStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"
    EXHAUSTED = "exhausted"  # gave up after max_attempts


class RetryTask(MongoDocument):
    task_id: str  # unique
    collector: str
    target: dict[str, Any] = Field(default_factory=dict)  # CollectorTarget payload
    attempts: int = 0
    max_attempts: int = 5
    backoff_seconds: float = 0.0  # delay applied before next_attempt_at
    next_attempt_at: datetime | None = None
    last_error: str | None = None
    status: RetryStatus = RetryStatus.PENDING
