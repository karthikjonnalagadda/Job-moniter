"""JazzHR collector (public Resumator API).

    GET https://api.resumatorapi.com/v1/jobs?apikey={api_key}

Returns a JSON array of jobs in one response (no pagination). Requires an API
key, supplied per-target in ``extra``:

    extra = {"api_key": "..."}
"""

from __future__ import annotations

from typing import Any

from app.collectors.ats.base_ats import BaseATSCollector, parse_iso
from app.collectors.base import CollectorTarget, HealthStatus, RawJob
from app.collectors.registry import register
from app.core.exceptions import CollectorError
from app.models.enums import ATSType, LegalMode, SourceType


@register("jazzhr")
class JazzHrCollector(BaseATSCollector):
    name = "jazzhr"
    version = "1.0.0"
    api_version = "v1"
    minimum_registry_version = "1.0.0"
    source_type = SourceType.ATS
    legal_mode = LegalMode.API
    priority = 16
    supported_api = "jazzhr-resumator-v1"
    supported_ats = ATSType.JAZZHR
    supports_authentication = True
    supports_bulk_fetch = True
    supports_job_description = True
    supports_posted_date = True
    rate_limit_rps = 2.0

    base_url = "https://api.resumatorapi.com/v1/jobs"

    async def validate_configuration(self) -> HealthStatus:
        return HealthStatus(healthy=True, detail="requires per-target api_key")

    async def _collect(self, target: CollectorTarget) -> list[dict[str, Any]]:
        api_key = target.extra.get("api_key")
        if not api_key:
            raise CollectorError("JazzHR target requires extra.api_key")
        url = f"{self.base_url}?apikey={api_key}"
        response = await self._request("GET", url, target=target)
        if response.status_code >= 400:
            raise CollectorError(f"JazzHR returned {response.status_code}")
        jobs = response.json()
        return list(jobs) if isinstance(jobs, list) else []

    def _to_raw_job(self, row: dict[str, Any], target: CollectorTarget) -> RawJob:
        parts = [row.get("city"), row.get("state"), row.get("country_id")]
        location_text = ", ".join(p for p in parts if p) or None
        board_code = row.get("board_code")
        url = f"https://app.jazz.co/apply/{board_code}" if board_code else row.get("apply_url", "")
        return RawJob(
            external_id=str(row["id"]),
            title=row.get("title", ""),
            company=target.company_name or row.get("hiring_lead") or "unknown",
            url=url,
            location=location_text,
            description=row.get("description"),
            posted_at=parse_iso(row.get("original_open_date") or row.get("open_date")),
            raw=row,
        )
