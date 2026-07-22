"""Edge-case coverage for Phase-7 reporting building blocks."""

from __future__ import annotations

import smtplib
from pathlib import Path

import pytest
from app.analytics.service import AnalyticsService
from app.config.settings import SmtpSettings
from app.exporters.base import Exporter
from app.exporters.json_exporter import JsonExporter
from app.notifications.smtp import SmtpNotifier
from app.reports.templating import TemplateRenderer
from app.reports.themes import theme, theme_names
from pydantic import SecretStr


def test_exporter_port_subclass(tmp_path: Path) -> None:
    class _Dummy(Exporter):
        extension = "txt"

        def export(self, jobs, destination):  # type: ignore[no-untyped-def]
            destination.write_text(str(len(list(jobs))))
            return destination

    out = _Dummy().export([{"a": 1}], tmp_path / "d.txt")
    assert out.read_text() == "1"


def test_templating_string_and_markdown() -> None:
    renderer = TemplateRenderer()
    assert renderer.render_string("Hi {{ name }}", {"name": "Sam"}) == "Hi Sam"
    html = renderer.render_markdown("# Title\n\nBody text")
    assert "Title" in html and "<" in html


def test_themes_fallback() -> None:
    assert theme("nope")["bg"] == theme("default")["bg"]
    assert "dark" in theme_names()


def test_json_export_jobs_streaming(tmp_path: Path) -> None:
    from app.models.job import Job

    job = Job(job_hash="h", external_id="1", source="s", company_name="C", role="R", url="u")
    out = JsonExporter(streaming=True).export_jobs([job], tmp_path / "s.ndjson")
    assert out.read_bytes().count(b"\n") == 1


async def test_analytics_empty(mock_db) -> None:
    from app.db.repositories.jobs import JobRepository
    from app.db.repositories.pipeline_runs import PipelineRunRepository

    service = AnalyticsService(JobRepository(mock_db), runs=PipelineRunRepository(mock_db))
    report = await service.build()
    assert report.total_jobs == 0
    assert report.average_match == 0.0
    assert report.pipeline_performance is not None
    assert report.pipeline_performance.total_runs == 0


async def test_smtp_health_check(monkeypatch: pytest.MonkeyPatch) -> None:
    class _OK:
        def __init__(self, *a: object, **k: object) -> None: ...
        def __enter__(self) -> _OK:
            return self

        def __exit__(self, *a: object) -> None: ...
        def noop(self) -> None: ...

    monkeypatch.setattr(smtplib, "SMTP", _OK)
    settings = SmtpSettings(host="h", port=25, password=SecretStr(""), to_address="a@b.com")
    assert await SmtpNotifier(settings).health_check() is True

    def _boom(*a: object, **k: object) -> None:
        raise OSError("no server")

    monkeypatch.setattr(smtplib, "SMTP", _boom)
    assert await SmtpNotifier(settings).health_check() is False
