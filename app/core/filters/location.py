"""Location filter — keep only postings in the allowed locations / remote."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from app.core.filters.base import FilterResult

if TYPE_CHECKING:
    from app.models.job import Job


class LocationFilter:
    """Keep postings whose location matches an allow-list (or remote).

    With no allow-list configured the filter is a pass-through (accept all). The
    allow-list is matched case-insensitively against the job's city, country,
    and location tags; ``allow_remote`` always admits remote postings.
    """

    name = "location"

    def __init__(
        self, *, allowed: Iterable[str] | None = None, allow_remote: bool = True
    ) -> None:
        self._allowed = {a.strip().lower() for a in allowed if a.strip()} if allowed else set()
        self._allow_remote = allow_remote

    def check(self, job: Job) -> FilterResult:
        if not self._allowed:
            return FilterResult(passed=True, filter_name=self.name, reason="no location filter")
        if self._allow_remote and (job.location.is_remote or "remote" in job.location_tags):
            return FilterResult(passed=True, filter_name=self.name, reason="remote")

        candidates = {
            value.lower()
            for value in (job.location.city, job.location.country, *job.location_tags)
            if value
        }
        if candidates & self._allowed:
            return FilterResult(passed=True, filter_name=self.name)
        return FilterResult(
            passed=False,
            filter_name=self.name,
            reason=f"location {sorted(candidates) or '?'} not in allow-list",
        )
