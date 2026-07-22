"""/metrics endpoint (JSON + Prometheus)."""

from __future__ import annotations


def test_metrics_json(app_client) -> None:
    resp = app_client.get("/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert "counters" in body and "gauges" in body and "summaries" in body
    # the request we just made was counted by the middleware
    assert body["counters"].get("api_requests_total", 0) >= 1


def test_metrics_prometheus(app_client) -> None:
    resp = app_client.get("/metrics", params={"format": "prometheus"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "api_requests_total" in resp.text
