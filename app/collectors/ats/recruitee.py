"""Recruitee collector (public Offers API).

    GET https://{company}.recruitee.com/api/offers/

Returns ``{"offers": [...]}`` in one response (no pagination). No authentication
for the public offers feed.
"""

from __future__ import annotations

from typing import Any

from app.collectors.ats.base_ats import BaseATSCollector, parse_iso
from app.collectors.base import CollectorTarget, RawJob
from app.collectors.registry import register
from app.core.exceptions import CollectorError
from app.models.enums import ATSType, LegalMode, SourceType


@register("recruitee")
class RecruiteeCollector(BaseATSCollector):
    name = "recruitee"
    version = "1.0.0"
    api_version = "offers-v1"
    minimum_registry_version = "1.0.0"
    source_type = SourceType.ATS
    legal_mode = LegalMode.API
    priority = 9
    supported_api = "recruitee-offers-v1"
    supported_ats = ATSType.RECRUITEE
    supports_bulk_fetch = True
    supports_remote = True
    supports_job_description = True
    supports_posted_date = True
    rate_limit_rps = 2.0

    base_url = "https://recruitee.com"

    async def _collect(self, target: CollectorTarget) -> list[dict[str, Any]]:
        token = target.board_token or target.company_slug
        if not token:
            raise CollectorError("Recruitee target requires a company subdomain (board_token)")
        url = f"https://{token}.recruitee.com/api/offers/"
        response = await self._request("GET", url, target=target)
        if response.status_code >= 400:
            raise CollectorError(f"Recruitee {token} returned {response.status_code}")
        offers = response.json().get("offers", [])
        return list(offers) if isinstance(offers, list) else []

    def _to_raw_job(self, row: dict[str, Any], target: CollectorTarget) -> RawJob:
        parts = [row.get("city"), row.get("country")]
        location_text = ", ".join(p for p in parts if p) or None
        return RawJob(
            external_id=str(row["id"]),
            title=row.get("title", ""),
            company=target.company_name or (target.board_token or "unknown"),
            url=row.get("careers_url") or row.get("careers_apply_url", ""),
            location="Remote" if row.get("remote") else location_text,
            description=row.get("description"),
            posted_at=parse_iso(row.get("published_at") or row.get("created_at")),
            raw=row,
        )
