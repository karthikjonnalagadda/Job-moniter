"""Role-relevance filter — keep only roles that match the candidate's target
profile (AI / Data / Backend / QA), reject unrelated functions (HR, Sales,
Marketing, Finance, Operations, Customer Support, Product/Program/Project
Management, …). Runs in the filter stage, i.e. *before* embedding and ranking,
so irrelevant postings never reach the vector/ranking stages.

Both the accept and reject vocabularies are injectable so they can be tuned from
``FiltersSettings`` without touching this module.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.core.filters.base import FilterResult

if TYPE_CHECKING:
    from app.models.job import Job

# Target roles for an early-career AI/ML / Data / Python-Backend / QA profile.
DEFAULT_TARGET_TERMS: tuple[str, ...] = (
    # AI / ML
    "ai engineer", "applied ai", "ai backend", "machine learning", "ml engineer",
    "mlops", "llm", "generative ai", "gen ai", "genai", "prompt engineer",
    "nlp", "natural language", "rag engineer", "computer vision", "deep learning",
    "ai/ml", "ai researcher", "research engineer",
    # Data
    "data scientist", "data science", "data analyst", "data engineer",
    "analytics engineer", "decision scientist", "business intelligence",
    "bi analyst", "bi developer", "ml scientist",
    # Backend / SWE
    "backend engineer", "backend developer", "back end engineer", "python developer",
    "python engineer", "software engineer", "software developer", "sde",
    "full stack", "fullstack", "full-stack", "api engineer", "platform engineer",
    "application developer", "programmer analyst",
    # QA / SDET
    "qa engineer", "qa automation", "quality engineer", "quality assurance",
    "automation test", "test engineer", "test automation", "sdet",
    "software test", "software development engineer in test",
)

# Hard-exclude functions outside the technical individual-contributor profile.
DEFAULT_EXCLUDED_TERMS: tuple[str, ...] = (
    "human resource", "hr business", "hr generalist", "recruit", "talent acquisition",
    "sourcer", "sales", "account executive", "account manager", "business development",
    "bdr", "sdr", "pre-sales", "presales", "solutions engineer", "solution engineer",
    "marketing", "seo", "content writer", "copywriter", "social media", "brand",
    "finance", "accountant", "accounting", "payroll", "tax", "audit", "legal",
    "counsel", "compliance", "procurement", "operations manager", "customer support",
    "customer success", "technical support", "help desk", "service desk",
    "business development", "benefits specialist", "administrative", "office manager",
    "graphic designer", "ux designer", "ui designer", "product designer",
    "product manager", "program manager", "project manager", "scrum master",
    "agile coach", "technical writer", "trainer", "teacher", "professor", "faculty",
    "nurse", "physician", "driver", "delivery", "warehouse", "field",
)


def _compile(terms: tuple[str, ...]) -> re.Pattern[str]:
    # Word-boundary-ish match; phrases match as substrings after normalising spaces.
    escaped = sorted((re.escape(t) for t in terms), key=len, reverse=True)
    return re.compile(r"(?<![a-z])(" + "|".join(escaped) + r")(?![a-z])", re.IGNORECASE)


class RoleRelevanceFilter:
    """Keep only postings whose title/role matches the target profile."""

    name = "role_relevance"

    def __init__(
        self,
        *,
        target_terms: tuple[str, ...] | None = None,
        excluded_terms: tuple[str, ...] | None = None,
    ) -> None:
        self._target = _compile(target_terms or DEFAULT_TARGET_TERMS)
        self._excluded = _compile(excluded_terms or DEFAULT_EXCLUDED_TERMS)

    def _title(self, job: Job) -> str:
        return f"{job.role or ''} {job.normalized_role or ''}".strip().lower()

    def check(self, job: Job) -> FilterResult:
        title = self._title(job)
        if not title:
            return FilterResult(passed=False, filter_name=self.name, reason="no role title")
        excl = self._excluded.search(title)
        if excl:
            return FilterResult(
                passed=False, filter_name=self.name,
                reason=f"unrelated function: {excl.group(0)}",
            )
        if self._target.search(title):
            return FilterResult(passed=True, filter_name=self.name)
        return FilterResult(
            passed=False, filter_name=self.name,
            reason="role not in target profile (AI/Data/Backend/QA)",
        )
