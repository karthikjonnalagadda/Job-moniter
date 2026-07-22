"""BambooHR collector (public careers list API).

    GET https://{subdomain}.bamboohr.com/careers/list

Returns ``{"result": [...], "meta": {...}}`` in one response (no pagination). No
authentication for the hosted careers list. Job detail (description) lives behind
``/careers/{id}/detail`` and is fetched in Phase 8.
"""

from __future__ import annotations

from typing import Any

from app.collectors.ats.base_ats import BaseATSCollector, parse_iso
from app.collectors.base import CollectorTarget, RawJob
from app.collectors.registry import register
from app.core.exceptions import CollectorError
from app.models.enums import ATSType, LegalMode, SourceType


@register("bamboohr")
class BambooHrCollector(BaseATSCollector):
    name = "bamboohr"
    version = "1.0.0"
    api_version = "careers-v1"
    minimum_registry_version = "1.0.0"
    source_type = SourceType.ATS
    legal_mode = LegalMode.API
    priority = 7
    supported_api = "bamboohr-careers-v1"
    supported_ats = ATSType.BAMBOOHR
    supports_bulk_fetch = True
    supports_remote = True
    supports_posted_date = True
    rate_limit_rps = 2.0

    base_url = "https://bamboohr.com"

    def _subdomain(self, target: CollectorTarget) -> str:
        token = target.board_token or target.company_slug
        if not token:
            raise CollectorError("BambooHR target requires a subdomain (board_token)")
        return token

    async def _collect(self, target: CollectorTarget) -> list[dict[str, Any]]:
        token = self._subdomain(target)
        url = f"https://{token}.bamboohr.com/careers/list"
        response = await self._request("GET", url, target=target)
        if response.status_code >= 400:
            raise CollectorError(f"BambooHR {token} returned {response.status_code}")
        result = response.json().get("result", [])
        return list(result) if isinstance(result, list) else []

    def _to_raw_job(self, row: dict[str, Any], target: CollectorTarget) -> RawJob:
        token = target.board_token or target.company_slug or ""
        location = row.get("location") or {}
        parts = [location.get("city"), location.get("state"), location.get("country")]
        location_text = ", ".join(p for p in parts if p) if isinstance(location, dict) else None
        is_remote = str(row.get("isRemote", "")).lower() in {"yes", "true", "1"}
        return RawJob(
            external_id=str(row["id"]),
            title=row.get("jobOpeningName", ""),
            company=target.company_name or token or "unknown",
            url=f"https://{token}.bamboohr.com/careers/{row['id']}",
            location="Remote" if is_remote else (location_text or None),
            description=None,
            posted_at=parse_iso(row.get("datePosted")),
            raw=row,
        )
