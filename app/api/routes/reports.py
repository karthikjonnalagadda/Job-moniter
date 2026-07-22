"""Report history endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import ReportHistoryRepositoryDep
from app.models.report_record import ReportRecord

router = APIRouter(tags=["reports"])


@router.get("", response_model=list[ReportRecord])
async def list_reports(
    repo: ReportHistoryRepositoryDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
) -> list[ReportRecord]:
    """Recent generated reports (newest first)."""

    return await repo.list_recent(limit=limit)


@router.get("/history", response_model=list[ReportRecord])
async def report_history(
    repo: ReportHistoryRepositoryDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ReportRecord]:
    """Full report history (paginated)."""

    return await repo.list_recent(limit=limit)


@router.get("/{report_id}", response_model=ReportRecord)
async def get_report(report_id: str, repo: ReportHistoryRepositoryDep) -> ReportRecord:
    """Fetch one report record; counts as a download access."""

    record = await repo.increment_download(report_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Report '{report_id}' not found")
    return record
