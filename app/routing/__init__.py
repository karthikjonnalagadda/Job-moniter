"""Company routing engine.

Decides which collector should service each company: prefer its ATS collector,
else the career-page collector, else skip and log the reason. The strategy order
is configurable via ``RoutingConfig``. Routing consults the source registry
(enablement) and the collector registry (availability) — it never runs a
collector.
"""

from app.routing.models import RoutingConfig, RoutingDecision, RoutingSummary
from app.routing.router import CompanyRouter

__all__ = ["CompanyRouter", "RoutingConfig", "RoutingDecision", "RoutingSummary"]
