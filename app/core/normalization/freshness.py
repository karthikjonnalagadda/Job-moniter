"""Freshness parsing — turn any 'posted' representation into an aware datetime.

Handles ISO-8601 strings, Unix epoch (seconds or milliseconds), native
datetimes, and human relative dates ("today", "yesterday", "2 days ago",
"3 weeks ago", "just posted"). Returns an aware UTC datetime, or None when the
input carries no usable signal. ``now`` is injectable for deterministic tests.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

_REL = re.compile(r"(\d+)\s*(hour|hr|day|week|month|year)s?\s*ago", re.IGNORECASE)
_UNIT_DAYS = {"hour": 1 / 24, "hr": 1 / 24, "day": 1, "week": 7, "month": 30, "year": 365}


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class FreshnessParser:
    """Parse heterogeneous 'posted date' inputs into an aware datetime."""

    def __init__(self, *, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or _utcnow

    def parse(self, value: Any) -> datetime | None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        if isinstance(value, int | float):
            return self._from_epoch(float(value))
        text = str(value).strip()
        return self._from_text(text)

    def _from_epoch(self, value: float) -> datetime | None:
        # Milliseconds if the magnitude is far beyond a plausible second-epoch.
        if value > 1e12:
            value /= 1000.0
        try:
            return datetime.fromtimestamp(value, tz=UTC)
        except (ValueError, OSError, OverflowError):
            return None

    def _from_text(self, text: str) -> datetime | None:
        lowered = text.lower()
        now = self._now()
        if lowered in {"today", "just posted", "just now", "new"}:
            return now
        if lowered == "yesterday":
            return now - timedelta(days=1)
        match = _REL.search(lowered)
        if match:
            amount = int(match.group(1))
            unit_days = _UNIT_DAYS[match.group(2).lower()]
            return now - timedelta(days=amount * unit_days)
        # Numeric string → epoch.
        if lowered.lstrip("-").isdigit():
            return self._from_epoch(float(lowered))
        # ISO-8601 (tolerate a trailing Z).
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    def age_hours(self, posted: datetime | None) -> float | None:
        if posted is None:
            return None
        delta = self._now() - (posted if posted.tzinfo else posted.replace(tzinfo=UTC))
        return delta.total_seconds() / 3600.0
