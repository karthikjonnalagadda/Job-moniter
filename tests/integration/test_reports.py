"""Report service (all formats + history) and notification service."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.analytics.service import AnalyticsService
from app.db.repositories.benchmarks import BenchmarkRepository
from app.db.repositories.jobs import JobRepository
from app.db.repositories.pipeline_runs import PipelineRunRepository
from app.db.repositories.reports import ReportHistoryRepository
from app.models.common import Location
from app.models.job import Job, MatchDetail
from app.models.report_record import DeliveryStatus, ReportFormat
from app.notifications.base import NotificationMessage, Notifier
from app.notifications.service import NotificationService
from app.reports.dataset import ReportDatasetBuilder
from app.reports.service import ReportService


class _FakeNotifier(Notifier):
    channel = "fake"

    def __init__(self) -> None:
        self.messages: list[NotificationMessage] = []

    async def send(self, message: NotificationMessage) -> None:
        self.messages.append(message)

    async def health_check(self) -> bool:
        return True


async def _service(db, tmp_path: Path) -> ReportService:  # type: ignore[no-untyped-def]
    repo = JobRepository(db)
    for i, c in enumerate(["Google", "Flipkart", "Zomato"]):
        await repo.upsert_by_hash(
            Job(
                job_hash=f"h{i}", external_id=str(i), source="greenhouse", company_name=c,
                role="ML Engineer", normalized_role="ML Engineer", url=f"https://x/{i}",
                location=Location(city="Bangalore"), skills=["Python"], technologies=["Python"],
                posted_date=datetime(2026, 7, 21, tzinfo=UTC),
                match=MatchDetail(score=90 - i * 10, missing_skills=["Docker"]),
            )
        )
    analytics = AnalyticsService(
        repo, runs=PipelineRunRepository(db), benchmarks=BenchmarkRepository(db)
    )
    builder = ReportDatasetBuilder(
        repo, analytics, runs=PipelineRunRepository(db), benchmarks=BenchmarkRepository(db)
    )
    return ReportService(builder, export_dir=tmp_path, history=ReportHistoryRepository(db))


@pytest.mark.parametrize("fmt", ["excel", "csv", "json", "html", "pdf"])
async def test_generate_each_format_and_records_history(mock_db, tmp_path, fmt) -> None:
    if fmt == "pdf":
        pytest.importorskip("reportlab")
    service = await _service(mock_db, tmp_path)
    result = await service.generate(fmt)
    assert Path(result.path).exists()
    assert result.record.file_location == str(result.path)
    assert result.record.pipeline_version != "0.0.0"  # version stamped
    assert result.record.generation_time >= 0
    stored = await ReportHistoryRepository(mock_db).get_by_report_id(result.record.report_id)
    assert stored is not None and stored.format == ReportFormat(fmt)


async def test_download_count_increments(mock_db, tmp_path) -> None:
    service = await _service(mock_db, tmp_path)
    result = await service.generate("json")
    repo = ReportHistoryRepository(mock_db)
    await repo.increment_download(result.record.report_id)
    updated = await repo.get_by_report_id(result.record.report_id)
    assert updated is not None and updated.download_count == 1


async def test_notification_service_sends_with_attachments(mock_db, tmp_path) -> None:
    service = await _service(mock_db, tmp_path)
    notifier = _FakeNotifier()
    record = await NotificationService(service, notifier).send_report(
        report_type="daily", recipient="user@example.com",
        attach_formats=[ReportFormat.CSV],
    )
    assert len(notifier.messages) == 1
    message = notifier.messages[0]
    assert message.body_html and "<title>" in message.body_html
    assert len(message.attachments) == 1
    assert record.delivery_status == DeliveryStatus.SENT
