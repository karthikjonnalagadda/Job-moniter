"""Collector state + schema-version API surface."""

from __future__ import annotations


def test_collector_state_endpoint(app_client) -> None:
    resp = app_client.get("/collectors/greenhouse/state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["collector"] == "greenhouse"
    assert body["state"] == "idle"  # default
    assert app_client.get("/collectors/unknown/state").status_code == 404


def test_all_collector_states_endpoint(app_client) -> None:
    # touch one state so the registry has an entry
    app_client.get("/collectors/greenhouse/state")
    states = app_client.get("/collector-states").json()
    assert any(s["collector"] == "greenhouse" for s in states)


def test_greenhouse_metadata_reflects_capabilities(app_client) -> None:
    meta = app_client.get("/collectors/greenhouse").json()
    assert meta["supported_ats"] == "greenhouse"
    assert meta["api_version"] == "job-board-v1"
    assert "incremental_sync" in meta["capabilities"]


def test_job_schema_version_default() -> None:
    from app.models.common import JOB_SCHEMA_VERSION
    from app.models.job import Job

    job = Job(
        job_hash="h", external_id="1", source="greenhouse", company_name="A", role="R", url="u"
    )
    assert job.schema_version == JOB_SCHEMA_VERSION == 3
