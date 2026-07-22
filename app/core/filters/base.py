"""Filter contract + result model."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from app.models.base import AppBaseModel

if TYPE_CHECKING:
    from app.models.job import Job


class FilterResult(AppBaseModel):
    """Whether a job passed a filter, and why not if it didn't."""

    passed: bool
    filter_name: str
    reason: str = ""


@runtime_checkable
class JobFilter(Protocol):
    """A predicate over a normalised job with an explanation."""

    name: str

    def check(self, job: Job) -> FilterResult: ...
