"""Source registry data models."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.models.base import AppBaseModel
from app.models.enums import ATSType, LegalMode, SourceType


class SyncState(AppBaseModel):
    """Incremental-sync watermark so collectors can skip unchanged data.

    Populated at runtime by collectors (Phase 5+). Conditional-GET fields
    (``etag`` / ``last_modified``) and an opaque ``cursor`` let ATS collectors
    fetch only what changed since ``last_successful_sync``.
    """

    last_successful_sync: datetime | None = None
    etag: str | None = None
    last_modified: str | None = None  # HTTP-date string from Last-Modified
    cursor: str | None = None  # opaque pagination/delta cursor


class ConcurrencyLimits(AppBaseModel):
    """Per-source throttling — some ATS APIs tolerate parallelism, others don't."""

    max_concurrency: int = 4
    requests_per_second: float = 2.0
    burst_limit: int = 4


class SourceDefinition(AppBaseModel):
    """One declared job source (career page, ATS, or job board).

    ``name`` is the stable key and matches the collector registry name that
    services this source. Enablement and priority are data, not code.
    """

    name: str
    enabled: bool = True
    priority: int = 100
    source_type: SourceType = SourceType.ATS
    legal_mode: LegalMode = LegalMode.API
    rate_limit_rps: float = 2.0
    ats_type: ATSType | None = None
    #: Per-source concurrency/throttling (Phase 4.1). ``requests_per_second``
    #: defaults from ``rate_limit_rps`` when not given explicitly.
    concurrency: ConcurrencyLimits | None = None
    #: Incremental-sync watermark, updated by collectors at runtime.
    sync_state: SyncState = Field(default_factory=SyncState)
    #: Free-form per-source options (base URLs, auth hints) for later phases.
    options: dict[str, str] = Field(default_factory=dict)

    def limits(self) -> ConcurrencyLimits:
        """Effective concurrency limits (falls back to ``rate_limit_rps``)."""

        if self.concurrency is not None:
            return self.concurrency
        return ConcurrencyLimits(
            requests_per_second=self.rate_limit_rps,
            burst_limit=max(1, int(self.rate_limit_rps)),
        )


class SourceRegistryStats(AppBaseModel):
    """Aggregate view of the registry (served by ``GET /registry/stats``)."""

    total: int
    enabled: int
    disabled: int
    by_source_type: dict[str, int]
    by_legal_mode: dict[str, int]
    scrape_sources: list[str]  # legal_mode == scrape (opt-in, audited)
