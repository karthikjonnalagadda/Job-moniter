"""CompanyRouter — maps companies to the collector that should service them."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from app.collectors.registry import available_collectors
from app.config.logging import get_logger
from app.models.enums import ATSType
from app.routing.models import (
    RoutingConfig,
    RoutingDecision,
    RoutingStrategy,
    RoutingSummary,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.models.company import Company
    from app.registry.service import SourceRegistry

log = get_logger("routing")


class CompanyRouter:
    """Applies configurable routing rules against the source registry."""

    def __init__(self, registry: SourceRegistry, config: RoutingConfig | None = None) -> None:
        self._registry = registry
        self._config = config or RoutingConfig()

    def route(self, company: Company) -> RoutingDecision:
        collectors = available_collectors()
        blocked_reasons: list[str] = []

        for strategy in self._config.order:
            candidate = self._candidate_for(strategy, company)
            if candidate is None:
                continue
            source = self._registry.get(candidate)
            if source is None or not source.enabled:
                blocked_reasons.append(f"{strategy}:'{candidate}' disabled/absent")
                continue
            registered = candidate in collectors
            if self._config.require_registered_collector and not registered:
                blocked_reasons.append(f"{strategy}:'{candidate}' collector not registered")
                continue
            return RoutingDecision(
                company_slug=company.slug,
                company_name=company.name,
                routed=True,
                collector=candidate,
                strategy=strategy,
                collector_available=registered,
                reason=f"matched {strategy} collector '{candidate}'",
            )

        reason = "; ".join(blocked_reasons) or "no ATS and no career URL"
        log.debug("Company '{}' skipped: {}", company.slug, reason)
        return RoutingDecision(
            company_slug=company.slug,
            company_name=company.name,
            routed=False,
            reason=reason,
        )

    def _candidate_for(self, strategy: RoutingStrategy | str, company: Company) -> str | None:
        """Return the collector name a strategy would use, or None if N/A.

        Uses ``==`` (not ``is``): ``use_enum_values`` means ``strategy`` may be a
        plain string or an enum member depending on how the config was built.
        """

        if strategy == RoutingStrategy.ATS:
            ats = company.ats_type  # str (models use enum *values*)
            if ats and ats != ATSType.UNKNOWN:
                return ats.value if isinstance(ats, ATSType) else str(ats)
            return None
        if strategy == RoutingStrategy.CAREER_PAGE:
            return self._config.career_collector if company.career_url else None
        return None

    def route_all(self, companies: Iterable[Company]) -> RoutingSummary:
        decisions = [self.route(c) for c in companies]
        routed = [d for d in decisions if d.routed]
        by_collector = Counter(d.collector for d in routed if d.collector)
        return RoutingSummary(
            total=len(decisions),
            routed=len(routed),
            skipped=len(decisions) - len(routed),
            by_collector=dict(by_collector),
            decisions=decisions,
        )
