"""JSON exporter — pretty, compact, and streaming (NDJSON).

Pretty/compact serialise the full report; streaming writes one JSON object per
line (NDJSON) for large job sets without holding the whole array in memory.
Uses ``orjson`` (a core dependency) for speed.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import orjson

from app.exporters.report_base import ReportExporter
from app.exporters.rows import job_to_row
from app.models.report_record import ReportFormat

if TYPE_CHECKING:
    from app.models.job import Job
    from app.reports.dataset import ReportData


def stream_ndjson(rows: Iterable[dict[str, Any]]) -> Iterator[bytes]:
    """Yield one compact JSON object per line (NDJSON)."""

    for row in rows:
        yield orjson.dumps(row) + b"\n"


class JsonExporter(ReportExporter):
    """Report/rows JSON export in pretty, compact, or streaming mode."""

    format = ReportFormat.JSON
    extension = "json"

    def __init__(self, *, pretty: bool = True, streaming: bool = False) -> None:
        self._pretty = pretty
        self._streaming = streaming
        if streaming:
            self.extension = "ndjson"

    def export_jobs(self, jobs: Sequence[Job], destination: Path) -> Path:
        if self._streaming:
            with destination.open("wb") as handle:
                for chunk in stream_ndjson(job_to_row(job) for job in jobs):
                    handle.write(chunk)
            return destination
        rows = [job_to_row(job) for job in jobs]
        destination.write_bytes(self._dumps(rows))
        return destination

    def export(self, data: ReportData, destination: Path) -> Path:
        if self._streaming:
            return self.export_jobs(data.jobs, destination)
        payload = {
            "meta": {
                "title": data.title,
                "generated_at": data.generated_at.isoformat() if data.generated_at else None,
                "run_id": data.run_id,
                "versions": data.versions.model_dump(),
            },
            "analytics": data.analytics.model_dump(),
            "jobs": [job_to_row(job) for job in data.jobs],
            "skill_gap": [s.model_dump() for s in data.skill_gap],
        }
        destination.write_bytes(self._dumps(payload))
        return destination

    def _dumps(self, obj: Any) -> bytes:
        option = orjson.OPT_INDENT_2 if self._pretty else 0
        return orjson.dumps(obj, option=option)
