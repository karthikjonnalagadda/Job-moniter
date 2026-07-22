"""Raw payload archiver.

Thin wrapper collectors use to persist upstream responses (when enabled). A
no-op when disabled or when no repository is wired, so collectors can always call
``archive(...)`` unconditionally.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.config.logging import get_logger
from app.core.context import current_correlation_id, current_run_id
from app.models.raw_payload import RawPayload

if TYPE_CHECKING:
    import httpx

    from app.db.repositories.raw_payloads import RawPayloadRepository

log = get_logger("collectors")


class RawArchiver:
    """Archive upstream responses for later debugging/replay."""

    def __init__(self, repo: RawPayloadRepository | None, *, enabled: bool) -> None:
        self._repo = repo
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled and self._repo is not None

    async def archive(
        self,
        *,
        collector: str,
        url: str,
        response: httpx.Response,
        source_slug: str | None = None,
    ) -> None:
        if not self.enabled or self._repo is None:
            return
        await self._repo.archive(
            RawPayload(
                collector=collector,
                source_slug=source_slug,
                url=url,
                content_type=response.headers.get("content-type"),
                status_code=response.status_code,
                etag=response.headers.get("etag"),
                last_modified=response.headers.get("last-modified"),
                body=response.text,
                run_id=current_run_id(),
                correlation_id=current_correlation_id(),
            )
        )
