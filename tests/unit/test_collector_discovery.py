"""Collector auto-discovery + capability metadata."""

from __future__ import annotations

from app.collectors.loader import discover_collectors
from app.collectors.registry import describe_all, get_collector_class


def test_discovery_registers_plugins() -> None:
    registry = discover_collectors(force=True)
    assert "linkedin" in registry  # discovered dynamically, not manually imported


def test_metadata_has_version_and_capabilities() -> None:
    discover_collectors()
    meta = get_collector_class("linkedin").describe()
    assert meta.version == "0.0.0"
    assert "authentication" in meta.capabilities
    assert "remote_filtering" in meta.capabilities
    assert meta.supported_ats is None


def test_describe_all_priority_sorted() -> None:
    discover_collectors()
    metas = describe_all()
    assert [m.priority for m in metas] == sorted(m.priority for m in metas)


async def test_health_check_aggregates_probes() -> None:
    discover_collectors()
    collector = get_collector_class("linkedin")()
    report = await collector.health_check()
    # disabled stub reports unhealthy via configuration + connectivity probes
    assert report.healthy is False
    assert report.configuration.healthy is False
    assert report.startup.healthy is True  # loaded fine
