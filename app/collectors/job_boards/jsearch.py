"""JSearch collector (OpenWeb Ninja / Google-for-Jobs aggregator).

JSearch aggregates Google for Jobs, so one query surfaces postings that originate
on LinkedIn, Indeed, Glassdoor, ZipRecruiter, etc. — a legal, sanctioned way to
get the breadth those sites won't expose directly.

    GET https://api.openwebninja.com/jsearch/search-v2
    Header: X-API-Key: <key>
    params: query, country=in, page, num_pages, date_posted,
            job_requirements=under_3_years_experience,no_experience

Budget guard: the free tier is 200 requests/month (~6/day). One query == one
request, so ``search`` runs only the small fixed ``jsearch_queries`` set (default
3), each with ``num_pages=1``. No key => the collector no-ops.

Every query is pinned to ``country=in`` + junior ``job_requirements`` so the
source pre-filters for entry-level Indian roles before the pipeline's own
junior/resume filters run.
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

_ENDPOINT = "https://api.openwebninja.com/jsearch/search-v2"
_JUNIOR_REQUIREMENTS = "under_3_years_experience,no_experience"


@register("jsearch")
class JSearchCollector(BaseCollector):
    """Fetch entry-level Indian jobs via the JSearch (Google-for-Jobs) aggregator."""

    name = "jsearch"
    version = "0.1.0"
    source_type = SourceType.JOB_BOARD
    legal_mode = LegalMode.API
    priority = 18
    supported_api = "jsearch"
    supports_authentication = True
    supports_pagination = True
    supports_posted_date = True
    supports_salary = True
    supports_remote = True
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
        self._api_key = settings.jsearch_key
        self._queries = settings.jsearch_query_list

    async def search(
        self, target: CollectorTarget
    ) -> list[RawJob]:  # global feed: target unused
        if not self._api_key:
            log.warning("jsearch: no JOBAGENT_JSEARCH_KEY configured — skipping")
            return []
        if self._http is None:  # pragma: no cover - executor always injects one
            raise RuntimeError("jsearch collector requires an HTTP client")

        seen: set[str] = set()
        jobs: list[RawJob] = []
        # One request per query (budget-critical: free tier is 200/month).
        for query in self._queries:
            params = {
                "query": query,
                "country": "in",
                "page": "1",
                "num_pages": "1",
                "date_posted": "week",
                "job_requirements": _JUNIOR_REQUIREMENTS,
            }
            resp = await self._http.get(
                _ENDPOINT, params=params, headers={"X-API-Key": self._api_key}
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"jsearch returned {resp.status_code} for query {query!r}"
                )
            # search-v2 nests postings under data.jobs (with a pagination cursor);
            # tolerate the older flat data=[...] shape too.
            data = resp.json().get("data") or {}
            rows = data.get("jobs", []) if isinstance(data, dict) else data
            for row in rows or []:
                job = self._to_raw(row)
                if job is not None and job.external_id not in seen:
                    seen.add(job.external_id)
                    jobs.append(job)
        log.info(
            "jsearch: collected {} jobs across {} queries",
            len(jobs),
            len(self._queries),
        )
        return jobs

    @staticmethod
    def _to_raw(row: dict[str, Any]) -> RawJob | None:
        url = (row.get("job_apply_link") or "").strip()
        title = (row.get("job_title") or "").strip()
        if not url or not title:
            return None
        location = ", ".join(
            p
            for p in (row.get("job_city"), row.get("job_state"), row.get("job_country"))
            if p
        )
        if row.get("job_is_remote"):
            location = f"Remote{(' / ' + location) if location else ''}"
        highlights = row.get("job_highlights") or {}
        parts = [
            row.get("job_description") or "",
            "\n".join(highlights.get("Qualifications", []) or []),
            "\n".join(highlights.get("Responsibilities", []) or []),
        ]
        description = "\n\n".join(p for p in parts if p).strip() or None
        return RawJob(
            external_id=str(row.get("job_id") or url),
            title=title,
            company=(row.get("employer_name") or "Unknown").strip(),
            url=url,
            location=location or None,
            description=description,
            posted_at=parse_iso(row.get("job_posted_at_datetime_utc")),
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
        if not self._api_key:
            return HealthStatus(healthy=False, detail="JOBAGENT_JSEARCH_KEY not set")
        return HealthStatus(
            healthy=True, detail=f"{len(self._queries)} queries configured"
        )
