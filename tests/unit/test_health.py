"""Smoke tests proving the Phase 2 scaffold boots and serves /health."""

from __future__ import annotations


def test_health_liveness(app_client) -> None:
    resp = app_client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.8.0"


def test_health_live_alias(app_client) -> None:
    # /health/live is the Kubernetes/Render-style liveness alias.
    resp = app_client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_readiness_reports_dependencies(app_client) -> None:
    resp = app_client.get("/health/ready")
    body = resp.json()
    # mongomock responds to ping, so readiness should be healthy.
    assert body["mongo"] is True
    assert body["vector_backend"] == "numpy"
    assert body["embedding_model"] == "BAAI/bge-small-en-v1.5"


def test_openapi_docs_available(app_client) -> None:
    assert app_client.get("/openapi.json").status_code == 200
