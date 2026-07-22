"""Experience filter — reject postings requiring more experience than allowed."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.filters.base import FilterResult
from app.models.enums import SeniorityLevel

if TYPE_CHECKING:
    from app.models.job import Job

_ENTRY_LEVELS = frozenset({SeniorityLevel.FRESHER, SeniorityLevel.ENTRY})


class ExperienceFilter:
    """Keep early-career roles; drop anything requiring > ``max_years``.

    A posting passes when its *minimum* required experience is within budget.
    If ``allow_if_entry_level`` is set, an explicit fresher/entry seniority
    passes even when the parsed years are missing or slightly above.
    """

    name = "experience"

    def __init__(self, *, max_years: float = 2.0, allow_if_entry_level: bool = True) -> None:
        self._max_years = max_years
        self._allow_entry = allow_if_entry_level

    def check(self, job: Job) -> FilterResult:
        exp = job.experience
        seniority = _as_level(job.seniority) or exp.level
        if self._allow_entry and seniority in _ENTRY_LEVELS:
            return FilterResult(passed=True, filter_name=self.name, reason="entry-level")

        if exp.min_years is None:
            # No signal → keep it (don't discard on missing data).
            return FilterResult(passed=True, filter_name=self.name, reason="experience unknown")

        if exp.min_years <= self._max_years:
            return FilterResult(passed=True, filter_name=self.name)
        return FilterResult(
            passed=False,
            filter_name=self.name,
            reason=f"requires {exp.min_years:g}y > max {self._max_years:g}y",
        )


def _as_level(value: object) -> SeniorityLevel | None:
    try:
        return SeniorityLevel(value)  # type: ignore[arg-type]
    except ValueError:
        return None
