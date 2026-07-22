"""Report scheduler due-logic (daily/weekly/monthly/manual)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.reports.scheduling import ReportSchedule, ReportScheduler, ScheduleFrequency

_SCHEDULER = ReportScheduler()
# 2026-07-22 is a Wednesday (weekday 2).
_NOW = datetime(2026, 7, 22, 7, 0, tzinfo=UTC)


def _s(freq: ScheduleFrequency, **kw: object) -> ReportSchedule:
    return ReportSchedule(schedule_id="s", frequency=freq, **kw)  # type: ignore[arg-type]


def test_daily_due_when_not_run_today() -> None:
    assert _SCHEDULER.is_due(_s(ScheduleFrequency.DAILY, hour=6), _NOW)
    ran = _s(ScheduleFrequency.DAILY, hour=6, last_run_at=_NOW.replace(hour=6, minute=30))
    assert not _SCHEDULER.is_due(ran, _NOW)  # already ran today


def test_daily_not_due_before_hour() -> None:
    assert not _SCHEDULER.is_due(_s(ScheduleFrequency.DAILY, hour=9), _NOW)  # 07:00 < 09:00


def test_weekly_due_on_weekday_only() -> None:
    wed = _s(ScheduleFrequency.WEEKLY, weekday=2, hour=6)  # Wednesday
    assert _SCHEDULER.is_due(wed, _NOW)
    thu = _s(ScheduleFrequency.WEEKLY, weekday=3, hour=6)  # Thursday
    assert not _SCHEDULER.is_due(thu, _NOW)


def test_monthly_due_on_day_of_month() -> None:
    due = _s(ScheduleFrequency.MONTHLY, day_of_month=22, hour=6)
    assert _SCHEDULER.is_due(due, _NOW)
    ran = _s(
        ScheduleFrequency.MONTHLY, day_of_month=22, hour=6,
        last_run_at=_NOW.replace(hour=6),
    )
    assert not _SCHEDULER.is_due(ran, _NOW)  # already ran this month


def test_manual_and_disabled_never_due() -> None:
    assert not _SCHEDULER.is_due(_s(ScheduleFrequency.MANUAL, hour=0), _NOW)
    assert not _SCHEDULER.is_due(_s(ScheduleFrequency.DAILY, hour=0, enabled=False), _NOW)


def test_due_filters_list() -> None:
    due = _SCHEDULER.due(
        _NOW,
        [
            _s(ScheduleFrequency.DAILY, hour=6),
            _s(ScheduleFrequency.MANUAL),
            _s(ScheduleFrequency.WEEKLY, weekday=3),  # not today
        ],
    )
    assert len(due) == 1
