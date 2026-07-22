"""Registry, company, import, and collector-health API endpoints."""

from __future__ import annotations

_CSV = (
    "company,slug,ats,ats_token,career_url\n"
    "Acme,acme,greenhouse,acme,https://acme.example/careers\n"
)


def test_registry_endpoints(app_client) -> None:
    sources = app_client.get("/registry").json()
    assert len(sources) == 24
    assert sources[0]["name"] == "career_site"  # priority 1

    stats = app_client.get("/registry/stats").json()
    assert stats["total"] == 24
    assert "linkedin" in stats["scrape_sources"]


def test_collector_health_endpoint(app_client) -> None:
    resp = app_client.get("/collectors/linkedin/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["healthy"] is False
    assert body["configuration"]["healthy"] is False
    assert app_client.get("/collectors/nope/health").status_code == 404


def test_company_validate_and_import_and_list(app_client) -> None:
    # validate only
    v = app_client.post("/companies/validate", files={"file": ("c.csv", _CSV, "text/csv")})
    assert v.status_code == 200 and v.json()["is_valid"] is True

    # import
    imp = app_client.post("/companies/import", files={"file": ("c.csv", _CSV, "text/csv")})
    assert imp.status_code == 200
    assert imp.json()["stats"]["inserted"] == 1

    # list + get
    listed = app_client.get("/companies").json()
    assert any(c["slug"] == "acme" for c in listed)
    assert app_client.get("/companies/acme").status_code == 200
    assert app_client.get("/companies/missing").status_code == 404


def test_company_sync_routes_to_ats(app_client) -> None:
    app_client.post("/companies/import", files={"file": ("c.csv", _CSV, "text/csv")})
    summary = app_client.post("/companies/sync").json()
    assert summary["routed"] >= 1
    assert summary["by_collector"].get("greenhouse", 0) >= 1


def test_import_rejects_unsupported_file_type(app_client) -> None:
    resp = app_client.post("/companies/import", files={"file": ("c.txt", "x", "text/plain")})
    assert resp.status_code == 415
