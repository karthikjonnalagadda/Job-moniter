"""SAP SuccessFactors collector (Recruiting OData v2 API).

    GET https://{host}/odata/v2/JobRequisitionPosting?$format=json&$top=100&$skip=N
    headers: Authorization: Basic <token>

SuccessFactors Recruiting is an authenticated OData service on a per-customer
API host, supplied per-target:

    extra = {"host": "api4.successfactors.com", "token": "<basic>"}

Registered but **disabled by default** in ``ats_sources.yaml``. Returns
``{"d": {"results": [...]}}`` and pages by ``$skip``.
"""

from __future__ import annotations

from typing import Any

from app.collectors.ats.base_ats import BaseATSCollector, parse_epoch_ms, parse_iso
from app.collectors.base import CollectorTarget, HealthStatus, RawJob
from app.collectors.registry import register
from app.core.exceptions import CollectorError
from app.models.enums import ATSType, LegalMode, SourceType

_PAGE_LIMIT = 100
_MAX_PAGES = 50


def _sap_date(value: Any) -> Any:
    """SAP OData dates arrive as ``/Date(1735732800000)/`` or ISO strings."""

    if isinstance(value, str) and value.startswith("/Date("):
        digits = value[6:].split(")")[0].split("+")[0]
        if digits.lstrip("-").isdigit():
            return parse_epoch_ms(int(digits))
    return parse_iso(value)


@register("successfactors")
class SuccessFactorsCollector(BaseATSCollector):
    name = "successfactors"
    version = "1.0.0"
    api_version = "odata-v2"
    minimum_registry_version = "1.0.0"
    source_type = SourceType.ATS
    legal_mode = LegalMode.API
    priority = 13
    supported_api = "successfactors-recruiting-odata-v2"
    supported_ats = ATSType.SUCCESSFACTORS
    supports_pagination = True
    supports_authentication = True
    supports_bulk_fetch = True
    supports_job_description = True
    supports_posted_date = True
    rate_limit_rps = 1.0

    base_url = "https://api.successfactors.com"

    def _endpoint(self, target: CollectorTarget) -> tuple[str, dict[str, str]]:
        host = target.extra.get("host")
        token = target.extra.get("token")
        if not (host and token):
            raise CollectorError("SuccessFactors target requires extra.host and extra.token")
        url = f"https://{host}/odata/v2/JobRequisitionPosting"
        return url, {"Authorization": f"Basic {token}"}

    async def validate_configuration(self) -> HealthStatus:
        return HealthStatus(healthy=True, detail="requires per-target host + token")

    async def _collect(self, target: CollectorTarget) -> list[dict[str, Any]]:
        base, headers = self._endpoint(target)
        rows: list[dict[str, Any]] = []
        for page in range(_MAX_PAGES):
            skip = page * _PAGE_LIMIT
            url = f"{base}?$format=json&$top={_PAGE_LIMIT}&$skip={skip}"
            response = await self._request("GET", url, target=target, headers=headers)
            if response.status_code >= 400:
                raise CollectorError(f"SuccessFactors returned {response.status_code}")
            results = (response.json().get("d") or {}).get("results", [])
            if not isinstance(results, list) or not results:
                break
            rows.extend(results)
            if len(results) < _PAGE_LIMIT:
                break
        return rows

    def _to_raw_job(self, row: dict[str, Any], target: CollectorTarget) -> RawJob:
        return RawJob(
            external_id=str(row.get("jobReqId") or row.get("jobPostingId")),
            title=row.get("jobTitle") or row.get("externalTitle", ""),
            company=target.company_name or (target.board_token or "unknown"),
            url=row.get("postingUrl") or row.get("externalPostingUrl", ""),
            location=row.get("location"),
            description=row.get("jobDescription") or row.get("externalJobDescription"),
            posted_at=_sap_date(row.get("boardPostingDate") or row.get("createdDateTime")),
            raw=row,
        )
