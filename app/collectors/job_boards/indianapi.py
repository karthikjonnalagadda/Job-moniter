"""IndianAPI jobs collector (https://jobs.indianapi.in).

A licensed India-focused job aggregator with sanctioned API-key access — a legal
alternative to scraping LinkedIn/Naukri. Single endpoint:

    GET https://jobs.indianapi.in/jobs
    Header: x-api-key: <key>

Returns a JSON array of postings, each shaped like::

    {"id", "title", "company", "about_company", "job_description",
     "job_title", "job_type", "location", "experience", "role_and_responsibility",
     "education_and_skills", "apply_link", "posted_date"}

The feed skews toward fresher / entry-level Indian roles, which matches this
project's junior-level target. The API key is read from settings
(``JOBAGENT_INDIANAPI_KEY``); with no key the collector no-ops so existing runs
are unaffected.

NOTE: the free tier is tiny (10 requests total) and the endpoint exposes no
documented pagination params, so ``search`` makes exactly one request per run.
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

_ENDPOINT = "https://jobs.indianapi.in/jobs"


@register("indianapi")
class IndianApiCollector(BaseCollector):
    """Fetch entry-level Indian jobs from the indianapi.in aggregator."""

    name = "indianapi"
    version = "0.1.0"
    source_type = SourceType.JOB_BOARD
    legal_mode = LegalMode.API
    priority = 19
    supported_api = "indianapi"
    supports_authentication = True
    supports_posted_date = True
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
        self._api_key = get_settings().indianapi_key

    async def search(
        self, target: CollectorTarget
    ) -> list[RawJob]:  # global feed: target unused
        if not self._api_key:
            log.warning("indianapi: no JOBAGENT_INDIANAPI_KEY configured — skipping")
            return []
        if self._http is None:  # pragma: no cover - executor always injects one
            raise RuntimeError("indianapi collector requires an HTTP client")

        resp = await self._http.get(_ENDPOINT, headers={"x-api-key": self._api_key})
        if resp.status_code != 200:
            raise RuntimeError(f"indianapi returned {resp.status_code}")
        payload = resp.json()
        if not isinstance(payload, list):
            raise RuntimeError("indianapi: unexpected response shape (expected a list)")

        jobs: list[RawJob] = []
        for row in payload:
            job = self._to_raw(row)
            if job is not None:
                jobs.append(job)
        log.info("indianapi: collected {} jobs", len(jobs))
        return jobs

    @staticmethod
    def _to_raw(row: dict[str, Any]) -> RawJob | None:
        apply_link = (row.get("apply_link") or "").strip()
        if not apply_link:
            return None
        # Prefer the clean role ("Trainee", "AI Engineer") for title so the
        # seniority/role filters parse it cleanly; keep the messy headline in raw.
        role = (row.get("job_title") or row.get("title") or "").strip()
        if not role:
            return None
        # Rich description so semantic resume-ranking + skill matching have signal.
        # Leading "Experience: Fresher" keeps entry-level roles past the seniority gate.
        parts = [
            f"Experience: {row.get('experience')}" if row.get("experience") else "",
            row.get("job_description") or "",
            row.get("role_and_responsibility") or "",
            row.get("education_and_skills") or "",
            row.get("about_company") or "",
        ]
        description = "\n\n".join(p for p in parts if p).strip() or None
        return RawJob(
            external_id=apply_link,  # stable across runs (the sequential id is not)
            title=role,
            company=(row.get("company") or "Unknown").strip(),
            url=apply_link,
            location=(row.get("location") or None),
            description=description,
            posted_at=parse_iso(row.get("posted_date")),
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
            return HealthStatus(healthy=False, detail="JOBAGENT_INDIANAPI_KEY not set")
        return HealthStatus(healthy=True, detail="api key present")
