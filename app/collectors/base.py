"""Collector plugin contract (Port).

Every job source — ATS, career site, or job board — is an independent plugin
implementing ``BaseCollector``. The pipeline never imports a concrete collector;
it discovers them through the registry and drives them through this interface.

Plugin contract (per Phase 2 spec) — four capabilities:
    * ``search()``       — fetch raw postings for a target.
    * ``normalize()``    — map one raw posting toward the canonical shape.
    * ``validate()``     — assert a normalized posting is usable.
    * ``health_check()`` — verify the source is reachable / not broken.

Concrete implementations arrive in Phases 5-7. This module defines the
interface and the loose ``RawJob`` DTO only — no collection logic in Phase 2.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import Field

from app.models.base import AppBaseModel
from app.models.enums import ATSType, LegalMode, SourceType


class CollectorTarget(AppBaseModel):
    """What a collector should fetch: an ATS board token, a career URL, etc."""

    company_slug: str | None = None
    company_name: str | None = None
    board_token: str | None = None
    url: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class RawJob(AppBaseModel):
    """Loose, source-shaped posting. Normalised into ``Job`` in Phase 8."""

    external_id: str
    title: str
    company: str
    url: str
    location: str | None = None
    description: str | None = None
    posted_at: datetime | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class HealthStatus(AppBaseModel):
    healthy: bool
    detail: str = ""


class CollectorHealthReport(AppBaseModel):
    """Aggregated result of a collector's four health probes."""

    name: str
    healthy: bool
    startup: HealthStatus
    configuration: HealthStatus
    dependencies: HealthStatus
    connectivity: HealthStatus


class CollectorMetadata(AppBaseModel):
    """Self-describing capabilities of a collector plugin (queryable via API).

    Assembled from class attributes by ``BaseCollector.describe()`` so a new
    collector declares its capabilities as attributes and gets a metadata record
    for free.
    """

    name: str
    version: str = "0.1.0"  # collector plugin version
    api_version: str | None = None  # upstream API version this speaks
    minimum_registry_version: str | None = None  # oldest host contract required
    source_type: SourceType
    legal_mode: LegalMode
    priority: int
    supported_api: str | None = None
    supported_ats: ATSType | None = None
    # ---- protocol/transport capabilities ----
    supports_pagination: bool = False
    supports_incremental_sync: bool = False
    supports_authentication: bool = False
    supports_remote_filtering: bool = False
    supports_bulk_fetch: bool = False
    # ---- data-field capabilities (what the source can supply) ----
    supports_salary: bool = False
    supports_posted_date: bool = False
    supports_remote: bool = False
    supports_company_logo: bool = False
    supports_job_description: bool = False
    supports_incremental_updates: bool = False
    rate_limit_rps: float = 2.0
    capabilities: list[str] = Field(default_factory=list)
    #: Static declaration; live status comes from ``health_check()``.
    health_status: str = "unknown"


class BaseCollector(ABC):
    """Abstract base every collector plugin extends."""

    #: Unique registry key, e.g. ``"greenhouse"``. Set on the subclass.
    name: str = "base"
    #: Semantic version of the collector plugin.
    version: str = "0.1.0"
    #: Upstream API version this collector speaks, if any.
    api_version: str | None = None
    #: Oldest host contract this collector requires (see app.collectors.versioning).
    minimum_registry_version: str | None = None
    #: Which priority tier / kind of source this is.
    source_type: SourceType = SourceType.ATS
    #: How data is obtained. ``SCRAPE`` collectors are disabled by default.
    legal_mode: LegalMode = LegalMode.API
    #: Collection order (1 = highest); mirrors ``ats_sources.yaml`` tiers.
    priority: int = 2
    #: Identifier of the upstream API this speaks, if any.
    supported_api: str | None = None
    #: Which ATS platform this collector serves (None for career sites/boards).
    supported_ats: ATSType | None = None
    # ---- protocol/transport capabilities ----
    supports_pagination: bool = False
    supports_incremental_sync: bool = False
    supports_authentication: bool = False
    supports_remote_filtering: bool = False
    supports_bulk_fetch: bool = False
    # ---- data-field capabilities (what the source can supply) ----
    supports_salary: bool = False
    supports_posted_date: bool = False
    supports_remote: bool = False
    supports_company_logo: bool = False
    supports_job_description: bool = False
    supports_incremental_updates: bool = False
    #: Default per-source request rate; overridable from ``ats_sources.yaml``.
    rate_limit_rps: float = 2.0

    # Capability flag name -> attribute, in a stable order for ``capabilities()``.
    _CAPABILITY_FLAGS: tuple[tuple[str, str], ...] = (
        ("pagination", "supports_pagination"),
        ("incremental_sync", "supports_incremental_sync"),
        ("authentication", "supports_authentication"),
        ("remote_filtering", "supports_remote_filtering"),
        ("bulk_fetch", "supports_bulk_fetch"),
        ("salary", "supports_salary"),
        ("posted_date", "supports_posted_date"),
        ("remote", "supports_remote"),
        ("company_logo", "supports_company_logo"),
        ("job_description", "supports_job_description"),
        ("incremental_updates", "supports_incremental_updates"),
    )

    @classmethod
    def capabilities(cls) -> list[str]:
        """Derive the capability tag list from the ``supports_*`` flags."""

        return [tag for tag, attr in cls._CAPABILITY_FLAGS if getattr(cls, attr)]

    @classmethod
    def describe(cls) -> CollectorMetadata:
        """Return this collector's static capability metadata."""

        return CollectorMetadata(
            name=cls.name,
            version=cls.version,
            api_version=cls.api_version,
            minimum_registry_version=cls.minimum_registry_version,
            source_type=cls.source_type,
            legal_mode=cls.legal_mode,
            priority=cls.priority,
            supported_api=cls.supported_api,
            supported_ats=cls.supported_ats,
            supports_pagination=cls.supports_pagination,
            supports_incremental_sync=cls.supports_incremental_sync,
            supports_authentication=cls.supports_authentication,
            supports_remote_filtering=cls.supports_remote_filtering,
            supports_bulk_fetch=cls.supports_bulk_fetch,
            supports_salary=cls.supports_salary,
            supports_posted_date=cls.supports_posted_date,
            supports_remote=cls.supports_remote,
            supports_company_logo=cls.supports_company_logo,
            supports_job_description=cls.supports_job_description,
            supports_incremental_updates=cls.supports_incremental_updates,
            rate_limit_rps=cls.rate_limit_rps,
            capabilities=cls.capabilities(),
        )

    @abstractmethod
    async def search(self, target: CollectorTarget) -> list[RawJob]:
        """Fetch raw postings for a single target."""

    @abstractmethod
    def normalize(self, raw: RawJob) -> dict[str, Any]:
        """Map a raw posting into a dict aligned with the canonical Job schema."""

    @abstractmethod
    def validate(self, raw: RawJob) -> bool:
        """Return True if the posting has the minimum required fields."""

    # ---- Health: four granular probes with healthy defaults -------------
    # Concrete collectors override the ones that apply; ``health_check``
    # aggregates them. This satisfies the Phase-4 requirement that every
    # collector supports startup/dependency/configuration/connectivity checks.
    async def validate_startup(self) -> HealthStatus:
        """Verify the plugin loaded and its class invariants hold."""

        return HealthStatus(healthy=True, detail="ok")

    async def validate_configuration(self) -> HealthStatus:
        """Verify required configuration (tokens, URLs) is present and sane."""

        return HealthStatus(healthy=True, detail="ok")

    async def validate_dependencies(self) -> HealthStatus:
        """Verify optional/required runtime dependencies are importable."""

        return HealthStatus(healthy=True, detail="ok")

    async def validate_connectivity(self) -> HealthStatus:
        """Verify the upstream source is reachable (cheap probe)."""

        return HealthStatus(healthy=True, detail="ok")

    async def health_check(self) -> CollectorHealthReport:
        """Run all four probes and aggregate them into one report."""

        startup = await self.validate_startup()
        configuration = await self.validate_configuration()
        dependencies = await self.validate_dependencies()
        connectivity = await self.validate_connectivity()
        healthy = all(
            probe.healthy
            for probe in (startup, configuration, dependencies, connectivity)
        )
        return CollectorHealthReport(
            name=self.name,
            healthy=healthy,
            startup=startup,
            configuration=configuration,
            dependencies=dependencies,
            connectivity=connectivity,
        )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<Collector name={self.name!r} type={self.source_type} legal={self.legal_mode}>"
