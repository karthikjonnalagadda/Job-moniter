"""Collector version compatibility + expanded capability flags."""

from __future__ import annotations

from app.collectors.loader import discover_collectors
from app.collectors.registry import get_collector_class
from app.collectors.versioning import REGISTRY_VERSION, is_compatible


def test_version_compatibility() -> None:
    assert is_compatible(None) is True  # no requirement
    assert is_compatible("1.0.0") is True
    assert is_compatible("0.9.0") is True
    assert is_compatible("99.0.0") is False
    assert REGISTRY_VERSION == "1.0.0"


def test_metadata_exposes_version_and_capability_fields() -> None:
    discover_collectors()
    meta = get_collector_class("linkedin").describe()
    # version-compat metadata present
    assert meta.api_version is None
    assert meta.minimum_registry_version is None
    # new data-field capability flags default to False
    assert meta.supports_salary is False
    assert meta.supports_job_description is False
    assert meta.supports_bulk_fetch is False
    # declared capabilities are surfaced in the tag list
    assert "authentication" in meta.capabilities
    assert "remote_filtering" in meta.capabilities
