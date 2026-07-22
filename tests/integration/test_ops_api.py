"""Ops API: benchmarks, import history, dead-letters, collector stats."""

from __future__ import annotations

_CSV = "company,slug,ats,ats_token\nAcme,acme,greenhouse,a\nBad,,lever\n"


def test_ops_endpoints_start_empty(app_client) -> None:
    assert app_client.get("/benchmarks").json() == []
    assert app_client.get("/imports").json() == []
    assert app_client.get("/dead-letters").json() == []
    assert app_client.get("/collectors/linkedin/stats").status_code == 404  # no run yet


def test_import_records_history_and_dead_letters(app_client) -> None:
    resp = app_client.post(
        "/companies/import",
        files={"file": ("c.csv", _CSV, "text/csv")},
        params={"skip_invalid": "true"},
    )
    body = resp.json()
    assert body["import_id"] is not None
    assert body["checksum"] is not None

    # import history records the run
    imports = app_client.get("/imports").json()
    assert any(i["import_id"] == body["import_id"] for i in imports)

    # the malformed row was dead-lettered
    dead = app_client.get("/dead-letters").json()
    assert len(dead) == 1
    assert dead[0]["kind"] == "import_row"


def test_import_record_lookup_by_id(app_client) -> None:
    body = app_client.post(
        "/companies/import", files={"file": ("c.csv", "company,slug\nAcme,acme\n", "text/csv")}
    ).json()
    got = app_client.get(f"/imports/{body['import_id']}")
    assert got.status_code == 200
    assert got.json()["import_id"] == body["import_id"]
    assert app_client.get("/imports/nonexistent").status_code == 404
