"""CSV exporter — plain, gzip-compressed, and streaming.

Streaming writes row-by-row (constant memory, suitable for very large datasets);
compression wraps the same stream in gzip. Satisfies both the row-oriented
``Exporter`` port and the report-level ``ReportExporter``.
"""

from __future__ import annotations

import csv
import gzip
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.exporters.report_base import ReportExporter
from app.exporters.rows import COLUMNS, job_to_row
from app.models.report_record import ReportFormat

if TYPE_CHECKING:
    from app.models.job import Job
    from app.reports.dataset import ReportData


def stream_csv_rows(rows: Iterable[dict[str, Any]]) -> Iterator[str]:
    """Yield CSV text line-by-line (header first). Constant memory."""

    import io

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(COLUMNS), extrasaction="ignore")
    writer.writeheader()
    yield _drain(buffer)
    for row in rows:
        writer.writerow(row)
        yield _drain(buffer)


def _drain(buffer: Any) -> str:
    value = buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)
    return value


class CsvExporter(ReportExporter):
    """Row-oriented CSV export (optionally gzip-compressed)."""

    format = ReportFormat.CSV
    extension = "csv"

    def __init__(self, *, compress: bool = False) -> None:
        self._compress = compress
        if compress:
            self.extension = "csv.gz"

    def export_jobs(self, jobs: Sequence[Job], destination: Path) -> Path:
        rows = (job_to_row(job) for job in jobs)
        opener = gzip.open if self._compress else open
        with opener(destination, "wt", encoding="utf-8", newline="") as handle:
            for chunk in stream_csv_rows(rows):
                handle.write(chunk)
        return destination

    def export(self, data: ReportData, destination: Path) -> Path:
        return self.export_jobs(data.jobs, destination)
