"""Pipeline run history — one record per processing run, with per-stage stats."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.models.base import AppBaseModel, MongoDocument
from app.models.common import DEFAULT_USER_ID
from app.models.enums import RunStatus


class StageStat(AppBaseModel):
    """Per-stage throughput + timing (independently benchmarked)."""

    name: str
    count_in: int = 0
    count_out: int = 0
    duration_ms: float = 0.0


class PipelineRun(MongoDocument):
    """A single job-processing pipeline execution."""

    run_id: str
    user_id: str = DEFAULT_USER_ID
    resume_id: str | None = None
    correlation_id: str | None = None

    status: RunStatus = RunStatus.RUNNING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float = 0.0

    # Funnel counts.
    collected: int = 0
    validated: int = 0
    normalized: int = 0
    filtered_out: int = 0
    duplicates: int = 0
    ranked: int = 0
    stored: int = 0

    stages: list[StageStat] = Field(default_factory=list)
    rejected_by: dict[str, int] = Field(default_factory=dict)
