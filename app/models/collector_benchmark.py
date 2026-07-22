"""Collector benchmarking model.

Rolling performance stats per collector, stored in ``collector_benchmarks`` and
updated after each run. Feeds future dashboards and source prioritisation.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import computed_field

from app.models.base import MongoDocument


class CollectorBenchmark(MongoDocument):
    collector: str  # unique key (collector name)
    runs: int = 0
    total_jobs_found: int = 0
    total_duplicates: int = 0
    total_errors: int = 0
    total_response_ms: float = 0.0
    response_samples: int = 0
    last_run_at: datetime | None = None

    # ---- derived rates (serialised in API responses) ----
    @computed_field  # type: ignore[prop-decorator]
    @property
    def average_response_ms(self) -> float:
        return self.total_response_ms / self.response_samples if self.response_samples else 0.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def success_rate(self) -> float:
        return (self.runs - self.total_errors) / self.runs if self.runs else 0.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def error_rate(self) -> float:
        return self.total_errors / self.runs if self.runs else 0.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def jobs_per_run(self) -> float:
        return self.total_jobs_found / self.runs if self.runs else 0.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duplicate_rate(self) -> float:
        return self.total_duplicates / self.total_jobs_found if self.total_jobs_found else 0.0
