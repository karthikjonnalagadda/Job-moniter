"""Notification service — generate a report and deliver it by email.

Builds the report dataset once, renders the HTML body, generates any requested
attachments (Excel/PDF/CSV) from the *same* dataset, and sends them through a
``Notifier`` (SMTP today). Records the delivery outcome on report history.
Supports daily / weekly / monthly / custom report types.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.config.logging import get_logger
from app.core.exceptions import NotificationError
from app.models.report_record import DeliveryStatus, ReportFormat, ReportRecord
from app.notifications.base import NotificationMessage

if TYPE_CHECKING:
    from app.notifications.base import Notifier
    from app.reports.service import ReportService

log = get_logger("notify")

_SUBJECTS = {
    "daily": "Daily Job Intelligence Report",
    "weekly": "Weekly Job Intelligence Report",
    "monthly": "Monthly Job Intelligence Report",
    "custom": "Job Intelligence Report",
}


class NotificationService:
    """Generate + deliver a report through a notification channel."""

    def __init__(self, reports: ReportService, notifier: Notifier) -> None:
        self._reports = reports
        self._notifier = notifier

    async def send_report(
        self,
        *,
        report_type: str = "daily",
        recipient: str | None = None,
        theme: str = "default",
        attach_formats: list[ReportFormat] | None = None,
        title: str | None = None,
    ) -> ReportRecord:
        attach_formats = attach_formats or [ReportFormat.EXCEL]

        # HTML body + shared dataset (reused for every attachment → one build).
        html_report = await self._reports.generate(
            ReportFormat.HTML, recipient=recipient, options={"theme": theme}
        )
        body_html = html_report.path.read_text(encoding="utf-8")

        attachments = []
        for fmt in attach_formats:
            produced = await self._reports.generate(fmt, data=html_report.data)
            attachments.append(produced.path)

        message = NotificationMessage(
            subject=title or _SUBJECTS.get(report_type, _SUBJECTS["custom"]),
            body_text=self._plain_summary(html_report.data),
            body_html=body_html,
            attachments=attachments,
        )

        try:
            await self._notifier.send(message)
        except NotificationError:
            await self._reports.mark_delivery(html_report.record.report_id, DeliveryStatus.FAILED)
            raise
        await self._reports.mark_delivery(html_report.record.report_id, DeliveryStatus.SENT)
        html_report.record.delivery_status = DeliveryStatus.SENT
        html_report.record.recipient = recipient
        log.info("Sent {} report to {}", report_type, recipient)
        return html_report.record

    @staticmethod
    def _plain_summary(data: object) -> str:
        a = getattr(data, "analytics", None)
        total = getattr(a, "total_jobs", 0)
        ranked = getattr(a, "ranked_jobs", 0)
        avg = getattr(a, "average_match", 0.0)
        return (
            f"Your Job Intelligence Report is attached.\n\n"
            f"Total jobs: {total}\nRanked jobs: {ranked}\nAverage match: {avg}\n\n"
            "Open the HTML email or the attached workbook for the full breakdown."
        )
