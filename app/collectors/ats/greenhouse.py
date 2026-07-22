"""Greenhouse collector (public Job Board API).

    GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true

Returns all live postings in one response (no pagination). Supports incremental
sync via HTTP ``ETag`` / ``Last-Modified`` conditional GETs — a ``304 Not
Modified`` means nothing changed since the last run.
"""

from __future__ import annotations

from typing import Any

from app.collectors.ats.base_ats import NOT_MODIFIED, BaseATSCollector, parse_iso
from app.collectors.base import CollectorTarget, RawJob
from app.collectors.registry import register
from app.core.exceptions import CollectorError
from app.models.enums import ATSType, LegalMode, SourceType


@register("greenhouse")
class GreenhouseCollector(BaseATSCollector):
    name = "greenhouse"
    version = "1.0.0"
    api_version = "job-board-v1"
    minimum_registry_version = "1.0.0"
    source_type = SourceType.ATS
    legal_mode = LegalMode.API
    priority = 2
    supported_api = "greenhouse-jobboard-v1"
    supported_ats = ATSType.GREENHOUSE
    supports_incremental_sync = True
    supports_bulk_fetch = True
    supports_job_description = True
    supports_posted_date = True
    rate_limit_rps = 2.0

    base_url = "https://boards-api.greenhouse.io/v1/boards"

    def _health_url(self) -> str:
        return f"{self.base_url}/greenhouse/jobs"

    async def _collect(self, target: CollectorTarget) -> list[dict[str, Any]]:
        token = target.board_token or target.company_slug
        if not token:
            raise CollectorError("Greenhouse target requires a board_token")
        url = f"{self.base_url}/{token}/jobs?content=true"
        response = await self._request(
            "GET", url, target=target, headers=self._conditional_headers(target)
        )
        if response.status_code == NOT_MODIFIED:
            return []  # nothing changed since last sync
        if response.status_code >= 400:
            raise CollectorError(f"Greenhouse {token} returned {response.status_code}")
        payload = response.json()
        jobs = payload.get("jobs", [])
        return list(jobs) if isinstance(jobs, list) else []

    def _to_raw_job(self, row: dict[str, Any], target: CollectorTarget) -> RawJob:
        location = row.get("location") or {}
        return RawJob(
            external_id=str(row["id"]),
            title=row["title"],
            company=target.company_name or (target.board_token or "unknown"),
            url=row.get("absolute_url", ""),
            location=location.get("name") if isinstance(location, dict) else None,
            description=row.get("content"),
            posted_at=parse_iso(row.get("updated_at") or row.get("first_published")),
            raw=row,
        )
