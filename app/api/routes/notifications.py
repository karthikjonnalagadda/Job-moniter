"""Notification endpoints — send a report by email (or preview channels)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import NotificationServiceDep
from app.core.exceptions import NotificationError
from app.models.report_record import ReportFormat, ReportRecord
from app.notifications.channels import available_channels

router = APIRouter(tags=["notifications"])


class SendRequest(BaseModel):
    report_type: str = "daily"  # daily | weekly | monthly | custom
    recipient: str | None = None
    theme: str = "default"
    attach_formats: list[ReportFormat] = Field(default_factory=lambda: [ReportFormat.EXCEL])
    title: str | None = None


@router.get("/channels", response_model=list[str])
async def channels() -> list[str]:
    """List notification channels (smtp implemented; others are interface stubs)."""

    return available_channels()


@router.post("/send", response_model=ReportRecord)
async def send(request: SendRequest, service: NotificationServiceDep) -> ReportRecord:
    """Generate a report and deliver it by email."""

    try:
        return await service.send_report(
            report_type=request.report_type,
            recipient=request.recipient,
            theme=request.theme,
            attach_formats=request.attach_formats,
            title=request.title,
        )
    except NotificationError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
