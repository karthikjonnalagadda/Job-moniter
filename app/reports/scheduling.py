"""Report scheduling — decide which report schedules are due to run.

Supports multiple named schedules (daily / weekly / monthly / manual), each with
its own formats, recipient, and theme. Actual firing is done by the GitHub
Actions cron (existing architecture) invoking the daily runner; this module only
decides *which* schedules are due at a given time, so it is pure and testable.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.models.base import AppBaseModel
from app.models.report_record import ReportFormat


class ScheduleFrequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    MANUAL = "manual"


class ReportSchedule(AppBaseModel):
    """A single recurring (or manual) report schedule."""

    schedule_id: str
    frequency: ScheduleFrequency
    formats: list[ReportFormat] = Field(default_factory=lambda: [ReportFormat.HTML])
    recipient: str | None = None
    theme: str = "default"
    hour: int = 6  # hour-of-day to fire (local to the runner)
    weekday: int = 0  # Monday=0 (weekly)
    day_of_month: int = 1  # (monthly)
    enabled: bool = True
    last_run_at: datetime | None = None


class ReportScheduler:
    """Decides which schedules are due at a given time (no side effects)."""

    def due(self, now: datetime, schedules: list[ReportSchedule]) -> list[ReportSchedule]:
        return [s for s in schedules if self.is_due(s, now)]

    def is_due(self, schedule: ReportSchedule, now: datetime) -> bool:
        if not schedule.enabled or schedule.frequency == ScheduleFrequency.MANUAL:
            return False
        if now.hour < schedule.hour:
            return False
        last = schedule.last_run_at
        if schedule.frequency == ScheduleFrequency.DAILY:
            return last is None or last.date() < now.date()
        if schedule.frequency == ScheduleFrequency.WEEKLY:
            if now.weekday() != schedule.weekday:
                return False
            return last is None or (now.date() - last.date()).days >= 7
        if schedule.frequency == ScheduleFrequency.MONTHLY:
            if now.day != schedule.day_of_month:
                return False
            return last is None or (last.year, last.month) != (now.year, now.month)
        return False  # pragma: no cover
