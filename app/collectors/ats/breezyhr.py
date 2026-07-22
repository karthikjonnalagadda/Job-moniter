"""BreezyHR collector (public JSON board).

    GET https://{company}.breezy.hr/json

Returns a JSON array of positions in one response (no pagination). No
authentication for the public board feed.
"""

from __future__ import annotations

from typing import Any

from app.collectors.ats.base_ats import BaseATSCollector, parse_iso
from app.collectors.base import CollectorTarget, RawJob
from app.collectors.registry import register
from app.core.exceptions import CollectorError
from app.models.enums import ATSType, LegalMode, SourceType


@register("breezyhr")
class BreezyHrCollector(BaseATSCollector):
    name = "breezyhr"
    version = "1.0.0"
    api_version = "json-v1"
    minimum_registry_version = "1.0.0"
    source_type = SourceType.ATS
    legal_mode = LegalMode.API
    priority = 15
    supported_api = "breezy-json-v1"
    supported_ats = ATSType.BREEZYHR
    supports_bulk_fetch = True
    supports_remote = True
    supports_job_description = True
    supports_posted_date = True
    rate_limit_rps = 2.0

    base_url = "https://breezy.hr"

    async def _collect(self, target: CollectorTarget) -> list[dict[str, Any]]:
        token = target.board_token or target.company_slug
        if not token:
            raise CollectorError("BreezyHR target requires a company subdomain (board_token)")
        url = f"https://{token}.breezy.hr/json"
        response = await self._request("GET", url, target=target)
        if response.status_code >= 400:
            raise CollectorError(f"BreezyHR {token} returned {response.status_code}")
        positions = response.json()
        return list(positions) if isinstance(positions, list) else []

    def _to_raw_job(self, row: dict[str, Any], target: CollectorTarget) -> RawJob:
        token = target.board_token or target.company_slug or ""
        location = row.get("location") or {}
        city = location.get("city") if isinstance(location, dict) else None
        country = (
            (location.get("country") or {}).get("name")
            if isinstance(location.get("country"), dict)
            else location.get("country")
        ) if isinstance(location, dict) else None
        location_text = ", ".join(p for p in (city, country) if p) or None
        is_remote = bool(location.get("is_remote")) if isinstance(location, dict) else False
        return RawJob(
            external_id=str(row["_id"]),
            title=row.get("name", ""),
            company=target.company_name or token or "unknown",
            url=row.get("url") or f"https://{token}.breezy.hr/p/{row['_id']}",
            location="Remote" if is_remote else location_text,
            description=row.get("description"),
            posted_at=parse_iso(row.get("published_date") or row.get("creation_date")),
            raw=row,
        )
