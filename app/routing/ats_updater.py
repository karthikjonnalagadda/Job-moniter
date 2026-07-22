"""Continuous ATS-metadata enrichment for stored companies.

Closes the loop on career-site routing requirement #5 ("continuously update ATS
metadata as new information becomes available"). Given a company whose ATS is
still unknown, it re-runs URL-based detection and — when confident — persists the
discovered ``ats_type`` / ``ats_token`` / ``career_platform`` so the next routing
pass prefers the first-class ATS collector over the generic career crawler.

Idempotent and conservative: it never overwrites an ATS a human/import already
set, and only writes when detection clears a confidence threshold.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.config.logging import get_logger
from app.models.base import AppBaseModel
from app.models.enums import ATSType
from app.routing.detector import ATSDetector

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.db.repositories.companies import CompanyRepository
    from app.models.company import Company

log = get_logger("routing")


class ATSUpdateResult(AppBaseModel):
    """Outcome of an enrichment sweep."""

    scanned: int
    updated: int
    updated_slugs: list[str]


class ATSMetadataUpdater:
    """Detects and persists ATS wiring for companies with an unknown ATS."""

    def __init__(
        self,
        repo: CompanyRepository,
        *,
        detector: ATSDetector | None = None,
        min_confidence: float = 0.9,
    ) -> None:
        self._repo = repo
        self._detector = detector or ATSDetector()
        self._min_confidence = min_confidence

    def _should_update(self, company: Company) -> bool:
        # Only fill gaps — never override an ATS already assigned.
        return company.ats_type == ATSType.UNKNOWN and bool(company.career_url)

    async def enrich(self, company: Company) -> Company | None:
        """Detect and persist ATS metadata for one company; return it if changed."""

        if not self._should_update(company):
            return None
        detection = self._detector.detect(company.career_url)
        if not detection.detected or detection.confidence < self._min_confidence:
            return None
        updated = await self._repo.apply_ats_metadata(
            company.slug,
            ats_type=detection.ats_type,
            ats_token=detection.token,
            career_platform=detection.platform,
        )
        if updated is not None:
            log.info(
                "Enriched '{}': ats={} token={}",
                company.slug,
                detection.ats_type.value,
                detection.token,
            )
        return updated

    async def enrich_many(self, companies: Iterable[Company]) -> ATSUpdateResult:
        scanned = 0
        updated_slugs: list[str] = []
        for company in companies:
            scanned += 1
            if await self.enrich(company) is not None:
                updated_slugs.append(company.slug)
        return ATSUpdateResult(
            scanned=scanned, updated=len(updated_slugs), updated_slugs=updated_slugs
        )
