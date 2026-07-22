"""Filter chain — run a job through an ordered set of filters (AND semantics)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from app.core.filters.base import FilterResult
from app.models.base import AppBaseModel

if TYPE_CHECKING:
    from app.core.filters.base import JobFilter
    from app.models.job import Job


class FilterOutcome(AppBaseModel):
    """The chain's decision for one job."""

    passed: bool
    results: list[FilterResult] = Field(default_factory=list)

    @property
    def rejected_by(self) -> str | None:
        for result in self.results:
            if not result.passed:
                return result.filter_name
        return None


class FilterSummary(AppBaseModel):
    """Aggregate outcome of running a batch through the chain."""

    total: int
    passed: int
    rejected: int
    rejected_by: dict[str, int] = Field(default_factory=dict)


class FilterChain:
    """Applies filters in order; a job must pass all to survive."""

    def __init__(self, filters: list[JobFilter]) -> None:
        self._filters = filters

    def evaluate(self, job: Job) -> FilterOutcome:
        results: list[FilterResult] = []
        passed = True
        for job_filter in self._filters:
            result = job_filter.check(job)
            results.append(result)
            if not result.passed:
                passed = False
                break  # short-circuit: first failure rejects
        return FilterOutcome(passed=passed, results=results)

    def apply(self, jobs: list[Job]) -> tuple[list[Job], FilterSummary]:
        kept: list[Job] = []
        rejected_by: dict[str, int] = {}
        for job in jobs:
            outcome = self.evaluate(job)
            if outcome.passed:
                kept.append(job)
            elif outcome.rejected_by is not None:
                rejected_by[outcome.rejected_by] = rejected_by.get(outcome.rejected_by, 0) + 1
        return kept, FilterSummary(
            total=len(jobs),
            passed=len(kept),
            rejected=len(jobs) - len(kept),
            rejected_by=rejected_by,
        )
