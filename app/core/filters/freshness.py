"""Freshness filter — drop postings older than a configured age threshold."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.core.filters.base import FilterResult

if TYPE_CHECKING:
    from app.models.job import Job


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class FreshnessFilter:
    """Keep postings newer than ``max_age_hours``.

    Postings with no ``posted_date`` pass (missing data is not staleness); the
    quality score separately penalises the missing field.
    """

    name = "freshness"

    def __init__(
        self, *, max_age_hours: float = 24.0, now: Callable[[], datetime] | None = None
    ) -> None:
        self._max_age_hours = max_age_hours
        self._now = now or _utcnow

    def check(self, job: Job) -> FilterResult:
        posted = job.posted_date
        if posted is None:
            return FilterResult(passed=True, filter_name=self.name, reason="no posted date")
        aware = posted if posted.tzinfo else posted.replace(tzinfo=UTC)
        age_hours = (self._now() - aware).total_seconds() / 3600.0
        if age_hours <= self._max_age_hours:
            return FilterResult(passed=True, filter_name=self.name)
        return FilterResult(
            passed=False,
            filter_name=self.name,
            reason=f"{age_hours:.0f}h old > max {self._max_age_hours:.0f}h",
        )
