"""Seniority filter — reject anything above entry/junior level *before* embedding
and ranking. Three independent signals, any of which rejects:

1. **Seniority enum** — MID / SENIOR / LEAD (parsed by normalization).
2. **Title markers** — Senior/Sr/Staff/Principal/Lead/Manager/Director/VP/Head/
   Chief/CxO/Architect/Distinguished/Fellow, plus numeric *level* markers
   (Engineer II/III, SDE-2, Level 3, L4) which denote mid/senior bands.
3. **Experience** — a required minimum > ``max_years`` parsed from the title or
   description ("3+ years", "5 years", "minimum 4 years"), or explicit
   "experienced professional" language.

Explicit early-career signals (fresher / graduate / intern / entry / junior /
associate / trainee / apprentice / new grad / campus) in the title suppress the
softer language checks so genuine junior postings are never dropped.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.core.filters.base import FilterResult
from app.models.enums import SeniorityLevel

if TYPE_CHECKING:
    from app.models.job import Job

_SENIOR_ENUM = frozenset(
    {SeniorityLevel.MID, SeniorityLevel.SENIOR, SeniorityLevel.LEAD}
)

DEFAULT_SENIOR_TERMS: tuple[str, ...] = (
    "senior", "sr", "staff", "principal", "lead", "leads", "leader",
    "manager", "management", "director", "architect", "vp", "vice president",
    "head", "chief", "cto", "ceo", "coo", "cfo", "cio", "ciso", "cxo", "president",
    "engineering manager", "product manager", "program manager", "project manager",
    "delivery manager", "people manager", "team lead", "tech lead", "technical lead",
    "solution architect", "solutions architect", "enterprise architect",
    "distinguished", "fellow", "expert",
)

# Numeric / roman level markers that denote mid+ bands (II/III/IV/V, 2-9,
# SDE-2, Level 3, L4). Level 1 / "I" (entry) is deliberately NOT matched.
_LEVEL_RE = re.compile(
    r"\b(?:sde|swe|engineer|developer|dev|scientist|analyst|programmer|consultant)"
    r"\s*[-–—]?\s*(?:[2-9]|ii|iii|iv|v|vi)\b"  # noqa: RUF001 - typographic dashes intentional
    r"|\blevel\s*[2-9]\b|\bl[2-9]\b"
    r"|\bs?mts\b|\bpmts\b"                       # (senior/principal) member of technical staff
    r"|\b(?:ic|pl)[-\s]?[2-9]\b"                 # IC2 / PL3 career-level codes
    r"|\b[2-9]\s*/\s*[2-9]\b",                   # multi-level bands e.g. "MTS 2/3/4", "II/III"
    re.I,
)

# Experience requirement in free text (mirrors the normalizer; lower bound wins).
_EXP_RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-|to|–|—)\s*\d+(?:\.\d+)?\s*\+?\s*(?:years?|yrs?)")  # noqa: RUF001
_EXP_PLUS = re.compile(r"(\d+(?:\.\d+)?)\s*\+\s*(?:years?|yrs?)")
_EXP_SINGLE = re.compile(r"(?:minimum|min\.?|at least|atleast)\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?)")
_EXPERIENCED = re.compile(
    r"\b(experienced professional|seasoned|veteran|extensive experience"
    r"|highly experienced|proven track record|expert-level)\b",
    re.I,
)
_ENTRY_KEYWORDS = re.compile(
    r"\b(fresher|freshers|graduate|new grad|campus|entry[- ]level|junior|jr\.?"
    r"|associate|trainee|intern|internship|apprentice|early career|early talent)\b",
    re.I,
)


def _compile(terms: tuple[str, ...]) -> re.Pattern[str]:
    escaped = sorted((re.escape(t) for t in terms), key=len, reverse=True)
    return re.compile(r"(?<![a-z])(" + "|".join(escaped) + r")(?![a-z])", re.IGNORECASE)


def _min_years_in_text(text: str) -> float | None:
    lows: list[float] = []
    for rx in (_EXP_RANGE, _EXP_PLUS, _EXP_SINGLE):
        for m in rx.finditer(text):
            lows.append(float(m.group(1)))
    return min(lows) if lows else None


class SeniorityTitleFilter:
    """Reject postings above entry/junior level (title, level, or experience)."""

    name = "seniority"

    def __init__(
        self, *, senior_terms: tuple[str, ...] | None = None, max_years: float = 2.0
    ) -> None:
        self._pattern = _compile(senior_terms or DEFAULT_SENIOR_TERMS)
        self._max_years = max_years

    def check(self, job: Job) -> FilterResult:
        def reject(reason: str) -> FilterResult:
            return FilterResult(passed=False, filter_name=self.name, reason=reason)

        title = f"{job.role or ''} {job.normalized_role or ''}"
        title_l = title.lower()

        if job.seniority in _SENIOR_ENUM:
            return reject(f"seniority '{job.seniority}'")

        hit = self._pattern.search(title_l)
        if hit:
            return reject(f"senior title marker: {hit.group(0)}")

        lvl = _LEVEL_RE.search(title_l)
        if lvl:
            return reject(f"level marker: {lvl.group(0).strip()}")

        # Parsed (normalized) experience requirement.
        if job.experience.min_years is not None and job.experience.min_years > self._max_years:
            return reject(f"requires {job.experience.min_years:g}y > max {self._max_years:g}y")

        # Text backstop over title + description (early part where requirements live).
        text = f"{title_l} {(job.description or '')[:2000].lower()}"
        yrs = _min_years_in_text(text)
        if yrs is not None and yrs > self._max_years:
            return reject(f"text requires {yrs:g}y > max {self._max_years:g}y")

        # "Experienced professional" language, unless an explicit entry signal is present.
        if _EXPERIENCED.search(text) and not _ENTRY_KEYWORDS.search(title_l):
            return reject("experienced-professional language")

        return FilterResult(passed=True, filter_name=self.name)
