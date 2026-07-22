"""Analytics value objects — aggregate views over stored jobs + runs.

Plain, serialisable records so the same analytics feed the JSON/HTML/Excel/PDF
exporters and the ``/analytics`` API without recomputation per format.
"""

from __future__ import annotations

from pydantic import Field

from app.models.base import AppBaseModel


class CountStat(AppBaseModel):
    """A label with a count (companies, roles, skills, locations, ...)."""

    label: str
    count: int


class SalaryStat(AppBaseModel):
    """Salary distribution for a currency/period bucket."""

    currency: str
    period: str
    count: int
    min_amount: float
    max_amount: float
    avg_amount: float
    median_amount: float


class TrendPoint(AppBaseModel):
    """A single time-bucketed data point (e.g. jobs posted on a date)."""

    bucket: str  # e.g. "2026-07-21"
    count: int
    value: float | None = None  # optional metric (avg match, etc.)


class MatchTrend(AppBaseModel):
    """Resume-match score distribution."""

    resume_id: str | None = None
    ranked_jobs: int
    avg_score: float
    max_score: float
    buckets: dict[str, int] = Field(default_factory=dict)  # "90-100" -> n


class PipelinePerf(AppBaseModel):
    """Rolled-up pipeline performance across recent runs."""

    total_runs: int
    total_collected: int
    total_stored: int
    total_duplicates: int
    total_filtered_out: int
    avg_duration_seconds: float
    avg_stage_ms: dict[str, float] = Field(default_factory=dict)


class AnalyticsReport(AppBaseModel):
    """The complete analytics surface (feeds reports + the /analytics API)."""

    total_jobs: int = 0
    ranked_jobs: int = 0
    average_match: float = 0.0
    companies: list[CountStat] = Field(default_factory=list)
    roles: list[CountStat] = Field(default_factory=list)
    technologies: list[CountStat] = Field(default_factory=list)
    skills: list[CountStat] = Field(default_factory=list)
    locations: list[CountStat] = Field(default_factory=list)
    employment_types: list[CountStat] = Field(default_factory=list)
    salaries: list[SalaryStat] = Field(default_factory=list)
    hiring_trends: list[TrendPoint] = Field(default_factory=list)
    match_trends: list[MatchTrend] = Field(default_factory=list)
    pipeline_performance: PipelinePerf | None = None
