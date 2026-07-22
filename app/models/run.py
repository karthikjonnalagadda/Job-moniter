"""Scheduler run history model.

One document per daily pipeline execution, capturing exactly the fields approved
in Phase 1 so runs are auditable long after the ephemeral GitHub Actions logs
expire. Stamped with ``run_id``/``correlation_id`` for cross-log correlation.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.models.base import MongoDocument
from app.models.enums import RunStatus


class SchedulerRun(MongoDocument):
    """Audit record for a single daily run."""

    run_id: str  # unique
    correlation_id: str | None = None
    status: RunStatus = RunStatus.RUNNING

    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None

    collectors_executed: list[str] = Field(default_factory=list)
    jobs_collected: int = 0
    duplicates_removed: int = 0
    ai_ranked: int = 0
    excel_generated: bool = False
    email_sent: bool = False
    failures: list[str] = Field(default_factory=list)
    retry_count: int = 0
