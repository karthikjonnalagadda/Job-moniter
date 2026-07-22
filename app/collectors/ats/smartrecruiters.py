"""SmartRecruiters collector (public Posting API).

    GET https://api.smartrecruiters.com/v1/companies/{companyId}/postings?limit=100&offset=N

Returns ``{"content": [...], "totalFound": N, "limit": L, "offset": O}`` and
pages by offset. No authentication for the public job-board postings feed.
"""

from __future__ import annotations

from typing import Any

from app.collectors.ats.base_ats import BaseATSCollector, parse_iso
from app.collectors.base import CollectorTarget, RawJob
from app.collectors.registry import register
from app.core.exceptions import CollectorError
from app.models.enums import ATSType, LegalMode, SourceType

_PAGE_LIMIT = 100
_MAX_PAGES = 50


@register("smartrecruiters")
class SmartRecruitersCollector(BaseATSCollector):
    name = "smartrecruiters"
    version = "1.0.0"
    api_version = "v1"
    minimum_registry_version = "1.0.0"
    source_type = SourceType.ATS
    legal_mode = LegalMode.API
    priority = 6
    supported_api = "smartrecruiters-postings-v1"
    supported_ats = ATSType.SMARTRECRUITERS
    supports_pagination = True
    supports_bulk_fetch = True
    supports_remote = True
    supports_job_description = True
    supports_posted_date = True
    rate_limit_rps = 2.0

    base_url = "https://api.smartrecruiters.com/v1/companies"

    def _health_url(self) -> str:
        return f"{self.base_url}/smartrecruiters/postings?limit=1"

    async def _collect(self, target: CollectorTarget) -> list[dict[str, Any]]:
        token = target.board_token or target.company_slug
        if not token:
            raise CollectorError("SmartRecruiters target requires a company id (board_token)")
        rows: list[dict[str, Any]] = []
        for page in range(_MAX_PAGES):
            offset = page * _PAGE_LIMIT
            url = f"{self.base_url}/{token}/postings?limit={_PAGE_LIMIT}&offset={offset}"
            response = await self._request("GET", url, target=target)
            if response.status_code >= 400:
                raise CollectorError(f"SmartRecruiters {token} returned {response.status_code}")
            content = response.json().get("content", [])
            if not isinstance(content, list) or not content:
                break
            rows.extend(content)
            if len(content) < _PAGE_LIMIT:
                break
        return rows

    def _to_raw_job(self, row: dict[str, Any], target: CollectorTarget) -> RawJob:
        location = row.get("location") or {}
        parts = [location.get("city"), location.get("region"), location.get("country")]
        location_text = ", ".join(p for p in parts if p) if isinstance(location, dict) else None
        return RawJob(
            external_id=str(row["id"]),
            title=row.get("name", ""),
            company=target.company_name or (target.board_token or "unknown"),
            url=row.get("ref") or row.get("applyUrl", ""),
            location=location_text or None,
            description=(row.get("jobAd") or {}).get("sections", {}).get("jobDescription")
            if isinstance(row.get("jobAd"), dict)
            else None,
            posted_at=parse_iso(row.get("releasedDate") or row.get("createdOn")),
            raw=row,
        )
