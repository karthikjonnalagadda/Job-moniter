"""Adaptive polling scheduler.

Computes each source's next poll interval from historical signals instead of a
fixed cadence:

* **Activity** — sources that yield more jobs per run are polled more often.
* **Errors**   — a high error rate lengthens the interval (backoff).
* **Rate limits** — the interval never implies a rate above the source's limit.

Pure and deterministic (time injected) so it is easily tested.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.models.base import AppBaseModel

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.models.collector_benchmark import CollectorBenchmark
    from app.registry.models import SourceDefinition


class ScheduleDecision(AppBaseModel):
    collector: str
    interval_seconds: float
    next_poll_at: datetime
    reason: str


class AdaptiveScheduler:
    """Derives a per-source polling interval from activity and error history."""

    def __init__(
        self,
        *,
        base_interval: float = 3600.0,
        min_interval: float = 300.0,
        max_interval: float = 86400.0,
        now: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        self._base = base_interval
        self._min = min_interval
        self._max = max_interval
        self._now = now

    def decide(
        self,
        collector: str,
        *,
        benchmark: CollectorBenchmark | None = None,
        source: SourceDefinition | None = None,
    ) -> ScheduleDecision:
        interval = self._base
        reasons: list[str] = ["base"]

        if benchmark is not None and benchmark.runs > 0:
            # More jobs/run -> poll more frequently (activity factor in (0, 1]).
            activity_factor = 1.0 / (1.0 + benchmark.jobs_per_run / 10.0)
            interval *= activity_factor
            reasons.append(f"activity x{activity_factor:.2f}")

            # Higher error rate -> back off (error factor >= 1).
            error_factor = 1.0 + benchmark.error_rate * 4.0
            interval *= error_factor
            if benchmark.error_rate > 0:
                reasons.append(f"error x{error_factor:.2f}")

        # Respect the source rate limit: never schedule tighter than 1 request.
        if source is not None and source.rate_limit_rps > 0:
            min_gap = 1.0 / source.rate_limit_rps
            interval = max(interval, min_gap)

        interval = max(self._min, min(self._max, interval))
        return ScheduleDecision(
            collector=collector,
            interval_seconds=round(interval, 2),
            next_poll_at=self._now() + timedelta(seconds=interval),
            reason=", ".join(reasons),
        )
