"""Lever collector (public Postings API).

    GET https://api.lever.co/v0/postings/{token}?mode=json&limit=&offset=

Returns a JSON array of postings. Supports offset pagination — we page until a
short page (or the safety cap) is reached.
"""

from __future__ import annotations

from typing import Any

from app.collectors.ats.base_ats import BaseATSCollector, parse_epoch_ms
from app.collectors.base import CollectorTarget, RawJob
from app.collectors.registry import register
from app.core.exceptions import CollectorError
from app.models.enums import ATSType, LegalMode, SourceType

_PAGE_LIMIT = 100
_MAX_PAGES = 50


@register("lever")
class LeverCollector(BaseATSCollector):
    name = "lever"
    version = "1.0.0"
    api_version = "v0"
    minimum_registry_version = "1.0.0"
    source_type = SourceType.ATS
    legal_mode = LegalMode.API
    priority = 3
    supported_api = "lever-postings-v0"
    supported_ats = ATSType.LEVER
    supports_pagination = True
    supports_bulk_fetch = True
    supports_job_description = True
    supports_posted_date = True
    rate_limit_rps = 2.0

    base_url = "https://api.lever.co/v0/postings"

    def _health_url(self) -> str:
        return f"{self.base_url}/leverdemo?mode=json&limit=1"

    async def _collect(self, target: CollectorTarget) -> list[dict[str, Any]]:
        token = target.board_token or target.company_slug
        if not token:
            raise CollectorError("Lever target requires a board_token")

        rows: list[dict[str, Any]] = []
        for page in range(_MAX_PAGES):
            offset = page * _PAGE_LIMIT
            url = f"{self.base_url}/{token}?mode=json&limit={_PAGE_LIMIT}&offset={offset}"
            response = await self._request("GET", url, target=target)
            if response.status_code >= 400:
                raise CollectorError(f"Lever {token} returned {response.status_code}")
            batch = response.json()
            if not isinstance(batch, list) or not batch:
                break
            rows.extend(batch)
            if len(batch) < _PAGE_LIMIT:
                break  # last page
        return rows

    def _to_raw_job(self, row: dict[str, Any], target: CollectorTarget) -> RawJob:
        categories = row.get("categories") or {}
        return RawJob(
            external_id=str(row["id"]),
            title=row.get("text", ""),
            company=target.company_name or (target.board_token or "unknown"),
            url=row.get("hostedUrl", ""),
            location=categories.get("location") if isinstance(categories, dict) else None,
            description=row.get("descriptionPlain") or row.get("description"),
            posted_at=parse_epoch_ms(row.get("createdAt")),
            raw=row,
        )
