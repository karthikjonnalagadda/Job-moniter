"""Jobvite collector (public v2 Job API).

    GET https://api.jobvite.com/api/v2/job?api={api}&sc={sc}&page=N

Returns ``{"requisitions": [...], "page": N, "pageCount": M}`` and pages by
number. Requires an API key + secret company code, supplied per-target:

    extra = {"api": "...", "sc": "..."}
"""

from __future__ import annotations

from typing import Any

from app.collectors.ats.base_ats import BaseATSCollector, parse_iso
from app.collectors.base import CollectorTarget, HealthStatus, RawJob
from app.collectors.registry import register
from app.core.exceptions import CollectorError
from app.models.enums import ATSType, LegalMode, SourceType

_MAX_PAGES = 50


@register("jobvite")
class JobviteCollector(BaseATSCollector):
    name = "jobvite"
    version = "1.0.0"
    api_version = "v2"
    minimum_registry_version = "1.0.0"
    source_type = SourceType.ATS
    legal_mode = LegalMode.API
    priority = 10
    supported_api = "jobvite-job-v2"
    supported_ats = ATSType.JOBVITE
    supports_pagination = True
    supports_authentication = True
    supports_bulk_fetch = True
    supports_job_description = True
    supports_posted_date = True
    rate_limit_rps = 2.0

    base_url = "https://api.jobvite.com/api/v2/job"

    def _credentials(self, target: CollectorTarget) -> tuple[str, str]:
        api = target.extra.get("api")
        sc = target.extra.get("sc")
        if not (api and sc):
            raise CollectorError("Jobvite target requires extra.api and extra.sc")
        return str(api), str(sc)

    async def validate_configuration(self) -> HealthStatus:
        return HealthStatus(healthy=True, detail="requires per-target api + sc")

    async def _collect(self, target: CollectorTarget) -> list[dict[str, Any]]:
        api, sc = self._credentials(target)
        rows: list[dict[str, Any]] = []
        for page in range(1, _MAX_PAGES + 1):
            url = f"{self.base_url}?api={api}&sc={sc}&page={page}"
            response = await self._request("GET", url, target=target)
            if response.status_code >= 400:
                raise CollectorError(f"Jobvite returned {response.status_code}")
            payload = response.json()
            requisitions = payload.get("requisitions", [])
            if not isinstance(requisitions, list) or not requisitions:
                break
            rows.extend(requisitions)
            if page >= int(payload.get("pageCount", page)):
                break
        return rows

    def _to_raw_job(self, row: dict[str, Any], target: CollectorTarget) -> RawJob:
        return RawJob(
            external_id=str(row.get("eId") or row.get("id")),
            title=row.get("title", ""),
            company=target.company_name or (target.board_token or "unknown"),
            url=row.get("jobUrl") or row.get("applyUrl", ""),
            location=row.get("location"),
            description=row.get("detail") or row.get("description"),
            posted_at=parse_iso(row.get("date")),
            raw=row,
        )
