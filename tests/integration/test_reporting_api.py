"""Reporting/analytics/exports/notifications API surface."""

from __future__ import annotations


def _seed_pipeline(app_client) -> None:
    """Run a small pipeline so there are stored jobs to report on."""

    app_client.post(
        "/pipeline/process",
        json={
            "items": [
                {
                    "external_id": "1", "title": "ML Engineer", "company": "Google",
                    "url": "https://boards.greenhouse.io/g/jobs/1",
                    "location": "Bengaluru, India",
                    "description": "Python FastAPI PyTorch RAG. 0-2 years.",
                    "posted": "today", "source": "greenhouse", "ats_type": "greenhouse",
                }
            ],
            "resume": {"resume_id": "ai", "text": "Python FastAPI RAG", "max_experience_years": 2},
            "persist": True,
        },
    )


def test_analytics_endpoints(app_client) -> None:
    _seed_pipeline(app_client)
    full = app_client.get("/analytics").json()
    assert full["total_jobs"] >= 1
    assert app_client.get("/analytics/skills").status_code == 200
    assert app_client.get("/analytics/companies").status_code == 200
    assert app_client.get("/analytics/locations").status_code == 200
    assert app_client.get("/analytics/salaries").status_code == 200
    trends = app_client.get("/analytics/trends").json()
    assert "hiring_trends" in trends and "match_trends" in trends


def test_export_endpoints_generate_files(app_client) -> None:
    _seed_pipeline(app_client)
    assert set(app_client.get("/exports").json()) >= {"excel", "csv", "json", "html", "pdf"}
    for fmt in ("excel", "csv", "json", "html"):
        resp = app_client.post(f"/exports/{fmt}")
        assert resp.status_code == 200, fmt
        body = resp.json()
        assert body["format"] == fmt
        assert body["file_location"] is not None


def test_reports_history_endpoints(app_client) -> None:
    _seed_pipeline(app_client)
    created = app_client.post("/exports/json").json()
    listing = app_client.get("/reports").json()
    assert any(r["report_id"] == created["report_id"] for r in listing)
    assert app_client.get("/reports/history").status_code == 200
    # fetching a report counts as a download
    fetched = app_client.get(f"/reports/{created['report_id']}").json()
    assert fetched["download_count"] == 1
    assert app_client.get("/reports/nonexistent").status_code == 404


def test_notification_channels_endpoint(app_client) -> None:
    channels = app_client.get("/notifications/channels").json()
    assert "smtp" in channels
    assert {"telegram", "slack", "discord", "whatsapp", "teams"} <= set(channels)


def test_notification_send_without_smtp_returns_502(app_client) -> None:
    _seed_pipeline(app_client)
    # No SMTP server in tests → delivery fails gracefully with 502.
    resp = app_client.post(
        "/notifications/send", json={"report_type": "daily", "recipient": "x@y.com"}
    )
    assert resp.status_code == 502
