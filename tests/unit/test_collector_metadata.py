"""Collector metadata model + /collectors API."""

from __future__ import annotations

from app.collectors import describe_all, get_collector_class


def test_describe_all_includes_linkedin() -> None:
    metas = describe_all()
    names = {m.name for m in metas}
    assert "linkedin" in names
    # priority-sorted
    priorities = [m.priority for m in metas]
    assert priorities == sorted(priorities)


def test_linkedin_metadata_fields() -> None:
    meta = get_collector_class("linkedin").describe()
    assert meta.legal_mode == "scrape"
    assert meta.priority == 24
    assert meta.supports_authentication is True


def test_collectors_endpoint(app_client) -> None:
    resp = app_client.get("/collectors")
    assert resp.status_code == 200
    payload = resp.json()
    assert any(c["name"] == "linkedin" for c in payload)


def test_single_collector_endpoint(app_client) -> None:
    assert app_client.get("/collectors/linkedin").status_code == 200
    assert app_client.get("/collectors/does-not-exist").status_code == 404
