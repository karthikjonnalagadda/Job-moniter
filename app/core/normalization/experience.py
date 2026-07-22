"""Experience normalization — free-text requirement → ``ExperienceRequirement``.

Maps phrases to a ``(min_years, max_years, SeniorityLevel)`` triple:

    "fresher" / "graduate"      → 0,   0-1,  FRESHER
    "entry level"               → 0,   1,    ENTRY
    "2-4 years"                 → 2,   4,    (level from min)
    "3+ years"                  → 3,   None, (level from min)
    "senior" / "lead"           → level only

Level is inferred from ``min_years`` when a number is present, else from words.
"""

from __future__ import annotations

import re

from app.models.common import ExperienceRequirement
from app.models.enums import SeniorityLevel

# All experience patterns require a year/experience context so salary figures
# (e.g. "25-35 LPA") are never mistaken for years.
# – en-dash / — em-dash are common in typographic ranges.
_RANGE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:-|to|–|—)\s*(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)"
)
_PLUS = re.compile(r"(\d+(?:\.\d+)?)\s*\+\s*(?:years?|yrs?)?(?:\s*(?:of\s*)?exp\w*)?")
_SINGLE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:years?|yrs?)")

_WORD_LEVEL = (
    ("fresher", SeniorityLevel.FRESHER, 0.0, 1.0),
    ("graduate", SeniorityLevel.FRESHER, 0.0, 1.0),
    ("intern", SeniorityLevel.FRESHER, 0.0, 1.0),
    ("entry", SeniorityLevel.ENTRY, 0.0, 1.0),
    ("junior", SeniorityLevel.JUNIOR, 1.0, 3.0),
    ("associate", SeniorityLevel.ASSOCIATE, 1.0, 3.0),
    ("mid", SeniorityLevel.MID, 3.0, 6.0),
    ("senior", SeniorityLevel.SENIOR, 6.0, 10.0),
    ("staff", SeniorityLevel.LEAD, 8.0, 12.0),
    ("principal", SeniorityLevel.LEAD, 10.0, 15.0),
    ("lead", SeniorityLevel.LEAD, 8.0, 12.0),
)


def _level_from_years(min_years: float) -> SeniorityLevel:
    if min_years < 1:
        return SeniorityLevel.ENTRY
    if min_years < 3:
        return SeniorityLevel.JUNIOR
    if min_years < 6:
        return SeniorityLevel.MID
    if min_years < 9:
        return SeniorityLevel.SENIOR
    return SeniorityLevel.LEAD


class ExperienceNormalizer:
    """Parse experience requirements from free text."""

    def parse(self, text: str | None) -> ExperienceRequirement:
        if not text or not str(text).strip():
            return ExperienceRequirement()
        raw = str(text).strip()
        lowered = raw.lower()

        range_match = _RANGE.search(lowered)
        if range_match:
            low = float(range_match.group(1))
            high = float(range_match.group(2))
            return ExperienceRequirement(
                min_years=low, max_years=high, level=_level_from_years(low), raw=raw
            )

        plus_match = _PLUS.search(lowered)
        if plus_match:
            low = float(plus_match.group(1))
            return ExperienceRequirement(
                min_years=low, max_years=None, level=_level_from_years(low), raw=raw
            )

        single_match = _SINGLE.search(lowered)
        if single_match:
            low = float(single_match.group(1))
            return ExperienceRequirement(
                min_years=low, max_years=low, level=_level_from_years(low), raw=raw
            )

        for keyword, level, low, high in _WORD_LEVEL:
            if keyword in lowered:
                return ExperienceRequirement(min_years=low, max_years=high, level=level, raw=raw)

        return ExperienceRequirement(raw=raw)
