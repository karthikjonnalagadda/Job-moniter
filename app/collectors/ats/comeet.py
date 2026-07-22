"""Comeet collector (public careers API).

    GET https://www.comeet.co/careers-api/2.0/company/{token}/positions?token={query_token}

Returns a JSON array of positions in one response (no pagination). The path
``token`` is the company UID; a separate query ``token`` may be required and is
read from ``extra`` (falling back to the company UID).
"""

from __future__ import annotations

from typing import Any

from app.collectors.ats.base_ats import BaseATSCollector, parse_iso
from app.collectors.base import CollectorTarget, RawJob
from app.collectors.registry import register
from app.core.exceptions import CollectorError
from app.models.enums import ATSType, LegalMode, SourceType


@register("comeet")
class ComeetCollector(BaseATSCollector):
    name = "comeet"
    version = "1.0.0"
    api_version = "2.0"
    minimum_registry_version = "1.0.0"
    source_type = SourceType.ATS
    legal_mode = LegalMode.API
    priority = 14
    supported_api = "comeet-careers-v2"
    supported_ats = ATSType.COMEET
    supports_bulk_fetch = True
    supports_remote = True
    supports_job_description = True
    supports_posted_date = True
    rate_limit_rps = 2.0

    base_url = "https://www.comeet.co/careers-api/2.0/company"

    async def _collect(self, target: CollectorTarget) -> list[dict[str, Any]]:
        token = target.board_token or target.company_slug
        if not token:
            raise CollectorError("Comeet target requires a company UID (board_token)")
        query_token = target.extra.get("token", token)
        url = f"{self.base_url}/{token}/positions?token={query_token}"
        response = await self._request("GET", url, target=target)
        if response.status_code >= 400:
            raise CollectorError(f"Comeet {token} returned {response.status_code}")
        positions = response.json()
        return list(positions) if isinstance(positions, list) else []

    def _to_raw_job(self, row: dict[str, Any], target: CollectorTarget) -> RawJob:
        location = row.get("location") or {}
        parts = [location.get("city"), location.get("country")]
        location_text = ", ".join(p for p in parts if p) if isinstance(location, dict) else None
        return RawJob(
            external_id=str(row["uid"]),
            title=row.get("name", ""),
            company=target.company_name or (target.board_token or "unknown"),
            url=row.get("url_comeet_hosted_page") or row.get("url_active_page", ""),
            location=location_text or None,
            description=row.get("details"),
            posted_at=parse_iso(row.get("time_updated") or row.get("date_updated")),
            raw=row,
        )
