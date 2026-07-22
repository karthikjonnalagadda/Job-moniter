"""Routing engine: ATS → career page → skip (configurable)."""

from __future__ import annotations

from app.models.company import Company
from app.models.enums import ATSType
from app.registry.models import SourceDefinition
from app.registry.service import SourceRegistry
from app.routing.models import RoutingConfig, RoutingStrategy
from app.routing.router import CompanyRouter


def _registry() -> SourceRegistry:
    reg = SourceRegistry()
    reg.add(SourceDefinition(name="greenhouse", priority=2, ats_type=ATSType.GREENHOUSE))
    reg.add(SourceDefinition(name="career_site", priority=1))
    reg.add(SourceDefinition(name="lever", enabled=False, priority=3, ats_type=ATSType.LEVER))
    return reg


def test_routes_to_ats_when_present() -> None:
    router = CompanyRouter(_registry())
    decision = router.route(Company(name="Acme", slug="acme", ats_type=ATSType.GREENHOUSE))
    assert decision.routed
    assert decision.collector == "greenhouse"
    assert decision.strategy == RoutingStrategy.ATS


def test_falls_back_to_career_page() -> None:
    router = CompanyRouter(_registry())
    decision = router.route(
        Company(name="NoAts", slug="noats", career_url="https://noats.example/careers")
    )
    assert decision.routed
    assert decision.collector == "career_site"
    assert decision.strategy == RoutingStrategy.CAREER_PAGE


def test_skips_when_ats_disabled_and_no_career_url() -> None:
    router = CompanyRouter(_registry())
    decision = router.route(Company(name="Lev", slug="lev", ats_type=ATSType.LEVER))
    assert decision.routed is False
    assert "disabled" in decision.reason


def test_configurable_order_prefers_career_page() -> None:
    config = RoutingConfig(order=[RoutingStrategy.CAREER_PAGE, RoutingStrategy.ATS])
    router = CompanyRouter(_registry(), config)
    decision = router.route(
        Company(name="Both", slug="both", ats_type=ATSType.GREENHOUSE, career_url="https://both.example")
    )
    assert decision.collector == "career_site"


def test_route_all_summary() -> None:
    router = CompanyRouter(_registry())
    summary = router.route_all(
        [
            Company(name="A", slug="a", ats_type=ATSType.GREENHOUSE),
            Company(name="B", slug="b", career_url="https://b.example"),
            Company(name="C", slug="c"),  # skipped
        ]
    )
    assert summary.total == 3
    assert summary.routed == 2
    assert summary.skipped == 1
    assert summary.by_collector["greenhouse"] == 1
