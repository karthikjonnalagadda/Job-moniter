"""iCIMS collector (authenticated customer Search API).

    GET https://api.icims.com/customers/{customer_id}/search/jobs?searchJson=...
    headers: Authorization: Bearer <token>

iCIMS has no anonymous public board feed — it requires customer API credentials,
so this collector is registered but **disabled by default** in
``ats_sources.yaml`` and only runs when a target supplies:

    extra = {"customer_id": "1234", "token": "<bearer>"}

Returns ``{"searchResults": [{"id": ...}, ...]}``. This adapter maps the search
result rows; full job detail (a second ``/jobs/{id}`` call) lands in Phase 8.
"""

from __future__ import annotations

from typing import Any

from app.collectors.ats.base_ats import BaseATSCollector, parse_iso
from app.collectors.base import CollectorTarget, HealthStatus, RawJob
from app.collectors.registry import register
from app.core.exceptions import CollectorError
from app.models.enums import ATSType, LegalMode, SourceType


@register("icims")
class IcimsCollector(BaseATSCollector):
    name = "icims"
    version = "1.0.0"
    api_version = "customer-v1"
    minimum_registry_version = "1.0.0"
    source_type = SourceType.ATS
    legal_mode = LegalMode.API
    priority = 11
    supported_api = "icims-customer-v1"
    supported_ats = ATSType.ICIMS
    supports_authentication = True
    supports_bulk_fetch = True
    supports_posted_date = True
    rate_limit_rps = 1.0

    base_url = "https://api.icims.com/customers"

    def _endpoint(self, target: CollectorTarget) -> tuple[str, dict[str, str]]:
        customer_id = target.extra.get("customer_id") or target.board_token
        token = target.extra.get("token")
        if not (customer_id and token):
            raise CollectorError("iCIMS target requires extra.customer_id and extra.token")
        url = f"{self.base_url}/{customer_id}/search/jobs"
        return url, {"Authorization": f"Bearer {token}"}

    async def validate_configuration(self) -> HealthStatus:
        return HealthStatus(healthy=True, detail="requires per-target customer_id + token")

    async def _collect(self, target: CollectorTarget) -> list[dict[str, Any]]:
        url, headers = self._endpoint(target)
        response = await self._request("GET", url, target=target, headers=headers)
        if response.status_code >= 400:
            raise CollectorError(f"iCIMS returned {response.status_code}")
        results = response.json().get("searchResults", [])
        return list(results) if isinstance(results, list) else []

    def _to_raw_job(self, row: dict[str, Any], target: CollectorTarget) -> RawJob:
        return RawJob(
            external_id=str(row.get("id") or row.get("jobId")),
            title=row.get("jobTitle") or row.get("title", ""),
            company=target.company_name or (target.board_token or "unknown"),
            url=row.get("url") or row.get("jobPostingUrl", ""),
            location=row.get("location"),
            description=row.get("description"),
            posted_at=parse_iso(row.get("postedDate") or row.get("datePosted")),
            raw=row,
        )
