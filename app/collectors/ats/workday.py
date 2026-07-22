"""Workday collector (public CXS job-board API).

    POST https://{host}/wday/cxs/{tenant}/{site}/jobs
    body: {"limit": 20, "offset": N, "searchText": "", "appliedFacets": {}}

Workday tenants live on per-customer hosts (``acme.wd1.myworkdayjobs.com``) with
a tenant + site path, so the target carries them in ``extra``:

    extra = {"host": "acme.wd1.myworkdayjobs.com", "tenant": "acme", "site": "External"}

Returns ``{"total": N, "jobPostings": [...]}`` and pages by offset.
"""

from __future__ import annotations

from typing import Any

from app.collectors.ats.base_ats import BaseATSCollector
from app.collectors.base import CollectorTarget, HealthStatus, RawJob
from app.collectors.registry import register
from app.core.exceptions import CollectorError
from app.models.enums import ATSType, LegalMode, SourceType

_PAGE_LIMIT = 20
_MAX_PAGES = 50


@register("workday")
class WorkdayCollector(BaseATSCollector):
    name = "workday"
    version = "1.0.0"
    api_version = "cxs-v1"
    minimum_registry_version = "1.0.0"
    source_type = SourceType.ATS
    legal_mode = LegalMode.API
    priority = 5
    supported_api = "workday-cxs-v1"
    supported_ats = ATSType.WORKDAY
    supports_pagination = True
    supports_bulk_fetch = True
    supports_job_description = False
    supports_posted_date = False
    rate_limit_rps = 1.0

    base_url = "https://www.myworkdayjobs.com"

    def _endpoint(self, target: CollectorTarget) -> str:
        host = target.extra.get("host")
        tenant = target.extra.get("tenant") or target.board_token or target.company_slug
        site = target.extra.get("site")
        if not (host and tenant and site):
            raise CollectorError("Workday target requires extra.host, extra.tenant and extra.site")
        return f"https://{host}/wday/cxs/{tenant}/{site}/jobs"

    async def validate_configuration(self) -> HealthStatus:
        return HealthStatus(healthy=True, detail="requires per-target host/tenant/site")

    async def _collect(self, target: CollectorTarget) -> list[dict[str, Any]]:
        endpoint = self._endpoint(target)
        rows: list[dict[str, Any]] = []
        for page in range(_MAX_PAGES):
            body = {
                "limit": _PAGE_LIMIT,
                "offset": page * _PAGE_LIMIT,
                "searchText": "",
                "appliedFacets": {},
            }
            response = await self._request("POST", endpoint, target=target, json=body)
            if response.status_code >= 400:
                raise CollectorError(f"Workday returned {response.status_code}")
            postings = response.json().get("jobPostings", [])
            if not isinstance(postings, list) or not postings:
                break
            rows.extend(postings)
            if len(postings) < _PAGE_LIMIT:
                break
        return rows

    def _to_raw_job(self, row: dict[str, Any], target: CollectorTarget) -> RawJob:
        host = target.extra.get("host", "")
        external_path = row.get("externalPath", "")
        bullet = row.get("bulletFields") or []
        external_id = str(bullet[0]) if bullet else external_path
        return RawJob(
            external_id=external_id,
            title=row.get("title", ""),
            company=target.company_name or (target.board_token or "unknown"),
            url=f"https://{host}{external_path}" if host and external_path else external_path,
            location=row.get("locationsText"),
            description=None,  # detail requires a second call (Phase 8)
            posted_at=None,  # Workday exposes relative text ("Posted 5 Days Ago")
            raw=row,
        )
