"""Export endpoints — generate a report file in a chosen format."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import ReportServiceDep
from app.models.report_record import ReportFormat, ReportRecord

router = APIRouter(tags=["exports"])


class ExportOptions(BaseModel):
    compress: bool = False  # CSV
    pretty: bool = True  # JSON
    streaming: bool = False  # CSV/JSON
    theme: str = "default"  # HTML


class ExportResponse(BaseModel):
    report_id: str
    format: ReportFormat
    file_location: str | None
    generation_time: float


def _to_response(record: ReportRecord) -> ExportResponse:
    return ExportResponse(
        report_id=record.report_id,
        format=record.format,
        file_location=record.file_location,
        generation_time=record.generation_time,
    )


@router.get("", response_model=list[str])
async def list_formats() -> list[str]:
    """List the supported export formats."""

    return [f.value for f in ReportFormat]


async def _export(
    fmt: ReportFormat, service: ReportServiceDep, options: ExportOptions
) -> ExportResponse:
    report = await service.generate(fmt, options=options.model_dump())
    return _to_response(report.record)


@router.post("/excel", response_model=ExportResponse)
async def export_excel(service: ReportServiceDep) -> ExportResponse:
    return await _export(ReportFormat.EXCEL, service, ExportOptions())


@router.post("/csv", response_model=ExportResponse)
async def export_csv(
    service: ReportServiceDep, options: ExportOptions | None = None
) -> ExportResponse:
    return await _export(ReportFormat.CSV, service, options or ExportOptions())


@router.post("/json", response_model=ExportResponse)
async def export_json(
    service: ReportServiceDep, options: ExportOptions | None = None
) -> ExportResponse:
    return await _export(ReportFormat.JSON, service, options or ExportOptions())


@router.post("/html", response_model=ExportResponse)
async def export_html(
    service: ReportServiceDep, options: ExportOptions | None = None
) -> ExportResponse:
    return await _export(ReportFormat.HTML, service, options or ExportOptions())


@router.post("/pdf", response_model=ExportResponse)
async def export_pdf(service: ReportServiceDep) -> ExportResponse:
    return await _export(ReportFormat.PDF, service, ExportOptions())
