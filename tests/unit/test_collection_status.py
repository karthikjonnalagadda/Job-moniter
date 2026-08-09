"""Deterministic collection-status classification (no I/O)."""

from __future__ import annotations

from app.importers.collection_status import (
    compute_active_status,
    has_ats_collection_path,
    is_dead_endpoint,
)


def test_workday_needs_tenant_and_board() -> None:
    assert has_ats_collection_path(
        {"ats_platform": "workday", "ats_tenant": "acme", "ats_board": "External"}
    )
    # tenant alone is not enough (the CXS API also needs the site/board).
    assert not has_ats_collection_path({"ats_platform": "workday", "ats_tenant": "acme"})


def test_token_collector_needs_token() -> None:
    assert has_ats_collection_path({"ats_platform": "greenhouse", "ats_token": "acmeco"})
    assert not has_ats_collection_path({"ats_platform": "greenhouse", "ats_token": "Unknown"})


def test_unknown_platform_has_no_path() -> None:
    assert not has_ats_collection_path({"ats_platform": "unknown", "ats_token": "x"})
    # oracle/successfactors need extra coordinates we don't store as a flat token.
    assert not has_ats_collection_path({"ats_platform": "oracle", "ats_token": "x"})


def test_dead_endpoint_detection() -> None:
    assert is_dead_endpoint({"career_status": "not_found"})
    assert is_dead_endpoint({"career_status": "Invalid"})
    assert not is_dead_endpoint({"career_status": "blocked"})   # WAF, not permanent
    assert not is_dead_endpoint({"career_status": "timeout"})   # transient
    assert not is_dead_endpoint({"career_status": "working"})


def test_active_status_keeps_collectible_dead_pages() -> None:
    # Dead corporate page but a working Workday board -> still active.
    assert compute_active_status(
        {"career_status": "not_found", "ats_platform": "workday",
         "ats_tenant": "acme", "ats_board": "External"}
    )
    # Dead page and no ATS fallback -> inactive.
    assert not compute_active_status({"career_status": "not_found", "ats_platform": "unknown"})
    # Healthy page -> active.
    assert compute_active_status({"career_status": "working", "ats_platform": "unknown"})
    # WAF-blocked (not permanently dead) -> active (may be reachable another way).
    assert compute_active_status({"career_status": "blocked", "ats_platform": "unknown"})
