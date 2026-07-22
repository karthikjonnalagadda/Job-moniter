"""Routing engine data models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from app.models.base import AppBaseModel


class RoutingStrategy(StrEnum):
    ATS = "ats"
    CAREER_PAGE = "career_page"


class RoutingConfig(AppBaseModel):
    """Configurable routing rules.

    ``order`` is the strategy precedence: the first strategy that matches wins.
    Default prefers a company's ATS, then falls back to its career page.
    """

    order: list[RoutingStrategy] = Field(
        default_factory=lambda: [RoutingStrategy.ATS, RoutingStrategy.CAREER_PAGE]
    )
    #: Career-page collector name used for the fallback strategy.
    career_collector: str = "career_site"
    #: If True, only route to collectors that are actually registered.
    require_registered_collector: bool = False


class RoutingDecision(AppBaseModel):
    """The routing outcome for one company."""

    company_slug: str
    company_name: str | None = None
    routed: bool
    collector: str | None = None  # target collector/source name
    strategy: RoutingStrategy | None = None
    collector_available: bool = False  # is the collector class registered?
    reason: str


class RoutingSummary(AppBaseModel):
    """Aggregate routing result over many companies."""

    total: int
    routed: int
    skipped: int
    by_collector: dict[str, int] = Field(default_factory=dict)
    decisions: list[RoutingDecision] = Field(default_factory=list)
