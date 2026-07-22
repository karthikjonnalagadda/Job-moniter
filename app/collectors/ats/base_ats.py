"""Shared base for ATS collectors.

Centralises everything the concrete ATS adapters (Greenhouse, Lever, Ashby, …)
have in common, so a new ATS is just source-specific fetch + parse:

* uses the shared ``HttpClient`` (circuit breaker + per-host rate limiting);
* archives raw responses when an archiver is wired;
* sends conditional-GET headers from the target's sync watermark and captures
  the response ``ETag`` / ``Last-Modified`` for the next incremental run;
* normalises source rows into the common ``RawJob`` model and validates them;
* provides a connectivity health probe.

Concrete collectors implement ``_collect`` (pagination + fetch → list of source
rows) and ``_to_raw_job`` (one row → ``RawJob``).
"""

from __future__ import annotations

from abc import abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.collectors.base import BaseCollector, CollectorTarget, HealthStatus, RawJob
from app.config.logging import get_logger
from app.core.exceptions import ConfigurationError

if TYPE_CHECKING:
    import httpx

    from app.collectors.archive import RawArchiver
    from app.http.client import HttpClient

log = get_logger("collectors")

NOT_MODIFIED = 304


def parse_iso(value: Any) -> datetime | None:
    """Parse an ISO-8601 string (with optional trailing ``Z``) to aware datetime."""

    if not isinstance(value, str) or not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_epoch_ms(value: Any) -> datetime | None:
    """Parse a millisecond epoch integer to an aware datetime."""

    if not isinstance(value, int | float):
        return None
    return datetime.fromtimestamp(value / 1000.0, tz=UTC)


class BaseATSCollector(BaseCollector):
    """Base class for documented-API ATS collectors."""

    #: Root URL of the ATS API (no trailing slash).
    base_url: str = ""

    def __init__(
        self,
        http: HttpClient | None = None,
        *,
        archive: RawArchiver | None = None,
    ) -> None:
        self._http = http
        self._archive = archive
        # Captured from the last response, for the next incremental run.
        self._last_etag: str | None = None
        self._last_modified: str | None = None

    # ---- HTTP helper ----------------------------------------------------
    async def _request(
        self,
        method: str,
        url: str,
        *,
        target: CollectorTarget | None = None,
        json: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        if self._http is None:
            raise ConfigurationError(f"Collector '{self.name}' requires an HTTP client")
        response = await self._http.request(method, url, json=json, headers=headers)
        if self._archive is not None:
            slug = None
            if target is not None:
                slug = target.board_token or target.company_slug
            await self._archive.archive(
                collector=self.name, url=url, response=response, source_slug=slug
            )
        etag = response.headers.get("etag")
        last_modified = response.headers.get("last-modified")
        if etag:
            self._last_etag = etag
        if last_modified:
            self._last_modified = last_modified
        return response

    def _conditional_headers(self, target: CollectorTarget) -> dict[str, str]:
        """Build If-None-Match / If-Modified-Since from the target's watermark."""

        headers: dict[str, str] = {}
        if not self.supports_incremental_sync:
            return headers
        etag = target.extra.get("etag")
        last_modified = target.extra.get("last_modified")
        if etag:
            headers["If-None-Match"] = str(etag)
        if last_modified:
            headers["If-Modified-Since"] = str(last_modified)
        return headers

    # ---- public contract ------------------------------------------------
    async def search(self, target: CollectorTarget) -> list[RawJob]:
        rows = await self._collect(target)
        jobs: list[RawJob] = []
        for row in rows:
            try:
                raw = self._to_raw_job(row, target)
            except Exception as exc:  # one bad row never sinks the batch
                log.warning("{}: skipping malformed row: {}", self.name, exc)
                continue
            if self.validate(raw):
                jobs.append(raw)
        log.info("{}: collected {} jobs for '{}'", self.name, len(jobs), target.board_token)
        return jobs

    def normalize(self, raw: RawJob) -> dict[str, Any]:
        """Map a RawJob toward the canonical Job shape (full mapping in Phase 8)."""

        return {
            "external_id": raw.external_id,
            "source": self.name,
            "role": raw.title,
            "company_name": raw.company,
            "url": raw.url,
            "description": raw.description,
            "posted_date": raw.posted_at,
        }

    def validate(self, raw: RawJob) -> bool:
        return bool(raw.external_id and raw.title and raw.url)

    def sync_watermark(self) -> dict[str, str | None]:
        """Return the etag/last_modified captured this run (for SyncState)."""

        return {"etag": self._last_etag, "last_modified": self._last_modified}

    # ---- health ---------------------------------------------------------
    def _health_url(self) -> str:
        return self.base_url

    async def validate_configuration(self) -> HealthStatus:
        if not self.base_url:
            return HealthStatus(healthy=False, detail="base_url not set")
        return HealthStatus(healthy=True, detail="ok")

    async def validate_connectivity(self) -> HealthStatus:
        if self._http is None:
            return HealthStatus(healthy=False, detail="no HTTP client bound")
        try:
            response = await self._http.request("GET", self._health_url())
        except Exception as exc:
            return HealthStatus(healthy=False, detail=str(exc))
        healthy = response.status_code < 500
        return HealthStatus(healthy=healthy, detail=f"status {response.status_code}")

    # ---- subclass hooks -------------------------------------------------
    @abstractmethod
    async def _collect(self, target: CollectorTarget) -> list[dict[str, Any]]:
        """Fetch (with pagination) and return the source's raw job rows."""

    @abstractmethod
    def _to_raw_job(self, row: dict[str, Any], target: CollectorTarget) -> RawJob:
        """Map one source row to the common RawJob model."""
