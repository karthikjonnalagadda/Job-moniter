"""Teamtailor collector (public JSON:API).

    GET https://api.teamtailor.com/v1/jobs?page[size]=30&page[number]=N
    headers: Authorization: Token token=<api_key>, X-Api-Version: 20210218

Teamtailor requires an API token, supplied per-target in ``extra``:

    extra = {"api_key": "..."}

Returns JSON:API ``{"data": [...], "links": {"next": ...}}`` and pages by number.
"""

from __future__ import annotations

from typing import Any

from app.collectors.ats.base_ats import BaseATSCollector, parse_iso
from app.collectors.base import CollectorTarget, HealthStatus, RawJob
from app.collectors.registry import register
from app.core.exceptions import CollectorError
from app.models.enums import ATSType, LegalMode, SourceType

_API_VERSION = "20210218"
_PAGE_SIZE = 30
_MAX_PAGES = 50


@register("teamtailor")
class TeamtailorCollector(BaseATSCollector):
    name = "teamtailor"
    version = "1.0.0"
    api_version = "v1"
    minimum_registry_version = "1.0.0"
    source_type = SourceType.ATS
    legal_mode = LegalMode.API
    priority = 8
    supported_api = "teamtailor-jsonapi-v1"
    supported_ats = ATSType.TEAMTAILOR
    supports_pagination = True
    supports_authentication = True
    supports_bulk_fetch = True
    supports_job_description = True
    supports_posted_date = True
    rate_limit_rps = 2.0

    base_url = "https://api.teamtailor.com/v1/jobs"

    def _auth_headers(self, target: CollectorTarget) -> dict[str, str]:
        api_key = target.extra.get("api_key")
        if not api_key:
            raise CollectorError("Teamtailor target requires extra.api_key")
        return {"Authorization": f"Token token={api_key}", "X-Api-Version": _API_VERSION}

    async def validate_configuration(self) -> HealthStatus:
        return HealthStatus(healthy=True, detail="requires per-target api_key")

    async def _collect(self, target: CollectorTarget) -> list[dict[str, Any]]:
        headers = self._auth_headers(target)
        rows: list[dict[str, Any]] = []
        for page in range(1, _MAX_PAGES + 1):
            url = f"{self.base_url}?page[size]={_PAGE_SIZE}&page[number]={page}"
            response = await self._request("GET", url, target=target, headers=headers)
            if response.status_code >= 400:
                raise CollectorError(f"Teamtailor returned {response.status_code}")
            payload = response.json()
            data = payload.get("data", [])
            if not isinstance(data, list) or not data:
                break
            rows.extend(data)
            if not (payload.get("links") or {}).get("next"):
                break
        return rows

    def _to_raw_job(self, row: dict[str, Any], target: CollectorTarget) -> RawJob:
        attributes = row.get("attributes") or {}
        links = row.get("links") or {}
        return RawJob(
            external_id=str(row["id"]),
            title=attributes.get("title", ""),
            company=target.company_name or (target.board_token or "unknown"),
            url=links.get("careersite-job-url") or attributes.get("apply-url", ""),
            location="Remote" if attributes.get("remote-status") == "fully" else None,
            description=attributes.get("body"),
            posted_at=parse_iso(attributes.get("created-at")),
            raw=row,
        )
