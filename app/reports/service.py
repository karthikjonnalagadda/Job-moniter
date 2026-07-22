"""Report service — generate a report in any format and record its history.

Assembles the dataset once, exports it to a file in the export directory, and
persists a ``ReportRecord`` (with version stamps) to report history. The same
service backs the ``/exports/*`` and ``/reports`` API and the email engine.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.config.logging import get_logger
from app.exporters.registry import build_exporter
from app.models.common import DEFAULT_USER_ID
from app.models.report_record import DeliveryStatus, ReportFormat, ReportRecord

if TYPE_CHECKING:
    from app.db.repositories.reports import ReportHistoryRepository
    from app.reports.dataset import ReportData, ReportDatasetBuilder

log = get_logger("api")


class GeneratedReport:
    """A produced report: its history record, on-disk path, and dataset."""

    def __init__(self, record: ReportRecord, path: Path, data: ReportData) -> None:
        self.record = record
        self.path = path
        self.data = data


class ReportService:
    """Generate reports and persist their history."""

    def __init__(
        self,
        builder: ReportDatasetBuilder,
        *,
        export_dir: Path,
        history: ReportHistoryRepository | None = None,
    ) -> None:
        self._builder = builder
        self._export_dir = export_dir
        self._history = history

    async def generate(
        self,
        fmt: ReportFormat | str,
        *,
        user_id: str = DEFAULT_USER_ID,
        recipient: str | None = None,
        options: dict[str, Any] | None = None,
        data: ReportData | None = None,
    ) -> GeneratedReport:
        fmt = ReportFormat(fmt)
        exporter = build_exporter(fmt, **(options or {}))
        report_data = data or await self._builder.build(user_id=user_id)

        report_id = uuid.uuid4().hex
        self._export_dir.mkdir(parents=True, exist_ok=True)
        destination = self._export_dir / f"report_{report_id}.{exporter.extension}"

        started = time.perf_counter()
        exporter.export(report_data, destination)
        elapsed = round(time.perf_counter() - started, 4)

        record = ReportRecord(
            report_id=report_id,
            run_id=report_data.run_id,
            user_id=user_id,
            generated_at=datetime.now(tz=UTC),
            format=fmt,
            recipient=recipient,
            delivery_status=DeliveryStatus.GENERATED,
            file_location=str(destination),
            generation_time=elapsed,
            report_version=report_data.versions.report_version,
            schema_version=report_data.versions.schema_version,
            pipeline_version=report_data.versions.pipeline_version,
            collector_versions=report_data.versions.collector_versions,
        )
        await self._save(record)
        log.info("Generated {} report {} in {}s", fmt.value, report_id, elapsed)
        return GeneratedReport(record, destination, report_data)

    async def mark_delivery(self, report_id: str, status: DeliveryStatus) -> None:
        if self._history is not None:
            record = await self._history.get_by_report_id(report_id)
            if record is not None and record.id is not None:
                await self._history.update(record.id, {"delivery_status": status.value})

    async def _save(self, record: ReportRecord) -> None:
        if self._history is not None:
            await self._history.insert(record)
