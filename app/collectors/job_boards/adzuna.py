"""Adzuna collector (India) — free job-board aggregator API.

Adzuna exposes a clean, documented JSON API with genuine India coverage and
salary data — a good free complement to JSearch.

    GET https://api.adzuna.com/v1/api/jobs/in/search/1
        ?app_id=<id>&app_key=<key>&results_per_page=50
        &what=<query>&max_days_old=7&sort_by=date

Needs BOTH ``adzuna_app_id`` and ``adzuna_app_key`` (free from
https://developer.adzuna.com); without them the collector no-ops. One query ==
one request; only the small fixed ``adzuna_queries`` set runs per run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.collectors.ats.base_ats import parse_iso
from app.collectors.base import BaseCollector, CollectorTarget, HealthStatus, RawJob
from app.collectors.registry import register
from app.config.logging import get_logger
from app.config.settings import get_settings
from app.models.enums import LegalMode, SourceType

if TYPE_CHECKING:
    from app.collectors.archive import RawArchiver
    from app.http.client import HttpClient

log = get_logger("collectors")

_ENDPOINT = "https://api.adzuna.com/v1/api/jobs/in/search/1"  # 'in' = India


@register("adzuna")
class AdzunaCollector(BaseCollector):
    """Fetch Indian jobs from the Adzuna API (free, salary-aware)."""

    name = "adzuna"
    version = "0.1.0"
    source_type = SourceType.JOB_BOARD
    legal_mode = LegalMode.API
    priority = 18
    supported_api = "adzuna"
    supports_authentication = True
    supports_pagination = True
    supports_posted_date = True
    supports_salary = True
    supports_job_description = True
    rate_limit_rps = 1.0

    def __init__(
        self,
        http: HttpClient | None = None,
        *,
        archive: RawArchiver | None = None,
    ) -> None:
        self._http = http
        self._archive = archive
        settings = get_settings()
        self._app_id = settings.adzuna_app_id
        self._app_key = settings.adzuna_app_key
        self._queries = settings.adzuna_query_list

    async def search(
        self, target: CollectorTarget
    ) -> list[RawJob]:  # global feed: target unused
        if not (self._app_id and self._app_key):
            log.warning("adzuna: JOBAGENT_ADZUNA_APP_ID/KEY not set — skipping")
            return []
        if self._http is None:  # pragma: no cover - executor always injects one
            raise RuntimeError("adzuna collector requires an HTTP client")

        seen: set[str] = set()
        jobs: list[RawJob] = []
        for query in self._queries:
            params = {
                "app_id": self._app_id,
                "app_key": self._app_key,
                "results_per_page": "50",
                "what": query,
                "max_days_old": "7",
                "sort_by": "date",
            }
            resp = await self._http.get(_ENDPOINT, params=params)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"adzuna returned {resp.status_code} for query {query!r}"
                )
            for row in resp.json().get("results", []) or []:
                job = self._to_raw(row)
                if job is not None and job.external_id not in seen:
                    seen.add(job.external_id)
                    jobs.append(job)
        log.info(
            "adzuna: collected {} jobs across {} queries", len(jobs), len(self._queries)
        )
        return jobs

    @staticmethod
    def _to_raw(row: dict[str, Any]) -> RawJob | None:
        url = (row.get("redirect_url") or "").strip()
        title = (row.get("title") or "").strip()
        if not url or not title:
            return None
        company = ((row.get("company") or {}).get("display_name") or "Unknown").strip()
        location = (row.get("location") or {}).get("display_name")
        return RawJob(
            external_id=str(row.get("id") or url),
            title=title,
            company=company,
            url=url,
            location=location,
            description=(row.get("description") or None),
            posted_at=parse_iso(row.get("created")),
            raw=row,
        )

    def normalize(self, raw: RawJob) -> dict[str, Any]:
        return {
            "external_id": raw.external_id,
            "source": self.name,
            "role": raw.title,
            "company_name": raw.company,
            "location": raw.location,
            "url": raw.url,
            "description": raw.description,
            "posted_date": raw.posted_at,
        }

    def validate(self, raw: RawJob) -> bool:
        return bool(raw.external_id and raw.title and raw.url)

    async def validate_configuration(self) -> HealthStatus:
        if not (self._app_id and self._app_key):
            return HealthStatus(
                healthy=False, detail="JOBAGENT_ADZUNA_APP_ID/KEY not set"
            )
        return HealthStatus(
            healthy=True, detail=f"{len(self._queries)} queries configured"
        )
