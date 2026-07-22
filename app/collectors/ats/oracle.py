"""Oracle Recruiting collector (Cloud CE REST API).

    GET https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions
        ?onlyData=true&finder=findReqs;siteNumber={site},limit=200,offset=N

Oracle Fusion Recruiting tenants live on per-customer hosts with a site number,
supplied per-target:

    extra = {"host": "acme.fa.us2.oraclecloud.com", "site": "CX_1001"}

Registered but **disabled by default** in ``ats_sources.yaml`` (enterprise
tenants vary). Returns ``{"items": [{"requisitionList": [...]}]}`` and pages by
offset.
"""

from __future__ import annotations

from typing import Any

from app.collectors.ats.base_ats import BaseATSCollector, parse_iso
from app.collectors.base import CollectorTarget, HealthStatus, RawJob
from app.collectors.registry import register
from app.core.exceptions import CollectorError
from app.models.enums import ATSType, LegalMode, SourceType

_PAGE_LIMIT = 200
_MAX_PAGES = 50


@register("oracle")
class OracleCollector(BaseATSCollector):
    name = "oracle"
    version = "1.0.0"
    api_version = "hcm-ce-v1"
    minimum_registry_version = "1.0.0"
    source_type = SourceType.ATS
    legal_mode = LegalMode.API
    priority = 12
    supported_api = "oracle-recruiting-ce-v1"
    supported_ats = ATSType.ORACLE
    supports_pagination = True
    supports_bulk_fetch = True
    supports_job_description = True
    supports_posted_date = True
    rate_limit_rps = 1.0

    base_url = "https://oraclecloud.com"

    def _params(self, target: CollectorTarget) -> tuple[str, str]:
        host = target.extra.get("host")
        site = target.extra.get("site")
        if not (host and site):
            raise CollectorError("Oracle target requires extra.host and extra.site")
        return str(host), str(site)

    async def validate_configuration(self) -> HealthStatus:
        return HealthStatus(healthy=True, detail="requires per-target host + site")

    async def _collect(self, target: CollectorTarget) -> list[dict[str, Any]]:
        host, site = self._params(target)
        base = f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
        rows: list[dict[str, Any]] = []
        for page in range(_MAX_PAGES):
            offset = page * _PAGE_LIMIT
            finder = f"findReqs;siteNumber={site},limit={_PAGE_LIMIT},offset={offset}"
            url = f"{base}?onlyData=true&finder={finder}"
            response = await self._request("GET", url, target=target)
            if response.status_code >= 400:
                raise CollectorError(f"Oracle returned {response.status_code}")
            items = response.json().get("items", [])
            requisitions: list[dict[str, Any]] = []
            for item in items if isinstance(items, list) else []:
                requisitions.extend(item.get("requisitionList", []))
            if not requisitions:
                break
            rows.extend(requisitions)
            if len(requisitions) < _PAGE_LIMIT:
                break
        return rows

    def _to_raw_job(self, row: dict[str, Any], target: CollectorTarget) -> RawJob:
        return RawJob(
            external_id=str(row.get("Id") or row.get("RequisitionId")),
            title=row.get("Title", ""),
            company=target.company_name or (target.board_token or "unknown"),
            url=row.get("RequisitionURL") or row.get("ExternalUrl", ""),
            location=row.get("PrimaryLocation"),
            description=row.get("ExternalDescriptionStr"),
            posted_at=parse_iso(row.get("PostedDate")),
            raw=row,
        )
