"""Ashby collector (public Job Board Posting API).

    POST https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true

Returns ``{"jobs": [...]}`` in one response (no pagination). Compensation is
included when requested, so salary is a supported capability.
"""

from __future__ import annotations

from typing import Any

from app.collectors.ats.base_ats import BaseATSCollector, parse_iso
from app.collectors.base import CollectorTarget, RawJob
from app.collectors.registry import register
from app.core.exceptions import CollectorError
from app.models.enums import ATSType, LegalMode, SourceType


@register("ashby")
class AshbyCollector(BaseATSCollector):
    name = "ashby"
    version = "1.0.0"
    api_version = "posting-api-v1"
    minimum_registry_version = "1.0.0"
    source_type = SourceType.ATS
    legal_mode = LegalMode.API
    priority = 4
    supported_api = "ashby-jobboard-v1"
    supported_ats = ATSType.ASHBY
    supports_bulk_fetch = True
    supports_salary = True
    supports_remote = True
    supports_job_description = True
    supports_posted_date = True
    rate_limit_rps = 2.0

    base_url = "https://api.ashbyhq.com/posting-api/job-board"

    def _health_url(self) -> str:
        return f"{self.base_url}/ashby"

    async def _collect(self, target: CollectorTarget) -> list[dict[str, Any]]:
        token = target.board_token or target.company_slug
        if not token:
            raise CollectorError("Ashby target requires a board_token")
        url = f"{self.base_url}/{token}?includeCompensation=true"
        response = await self._request("POST", url, target=target, json={})
        if response.status_code >= 400:
            raise CollectorError(f"Ashby {token} returned {response.status_code}")
        payload = response.json()
        jobs = payload.get("jobs", [])
        return list(jobs) if isinstance(jobs, list) else []

    def _to_raw_job(self, row: dict[str, Any], target: CollectorTarget) -> RawJob:
        return RawJob(
            external_id=str(row["id"]),
            title=row.get("title", ""),
            company=target.company_name or (target.board_token or "unknown"),
            url=row.get("jobUrl") or row.get("applyUrl", ""),
            location=row.get("location"),
            description=row.get("descriptionHtml") or row.get("descriptionPlain"),
            posted_at=parse_iso(row.get("publishedAt") or row.get("updatedAt")),
            raw=row,
        )
