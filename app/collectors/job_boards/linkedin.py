"""LinkedIn collector — INTERFACE STUB ONLY. Disabled; never runs.

Per the approved Phase 1/2 decision, LinkedIn exists as a *registered but
disabled* plugin so the collector surface is complete and uniform — but it
performs no collection whatsoever. There is deliberately no scraping logic here,
and none will be added without an explicit, compliant-access decision.

Guarantees enforced by this module:
    * It is registered under ``"linkedin"`` (visible to ``available_collectors``).
    * ``legal_mode = SCRAPE`` documents that any future implementation would be
      opt-in only. ``data/ats_sources.yaml`` keeps it ``enabled: false``.
    * Every operational method raises — so even if something enabled it by
      mistake, it cannot run. This is strictly stronger than "off in production".
"""

from __future__ import annotations

from typing import Any

from app.collectors.base import BaseCollector, CollectorTarget, HealthStatus, RawJob
from app.collectors.registry import register
from app.core.exceptions import ConfigurationError
from app.models.enums import LegalMode, SourceType

#: Documentation constant. Stays ``False``; the methods below hard-block anyway.
LINKEDIN_ENABLED = False

_DISABLED_MESSAGE = (
    "LinkedIn collector is a disabled interface stub and must not run. "
    "It is intentionally unimplemented (Phase 1/2 decision: interface only)."
)


@register("linkedin")
class LinkedInCollector(BaseCollector):
    """Disabled interface stub — completes the plugin surface, collects nothing."""

    version = "0.0.0"
    source_type = SourceType.JOB_BOARD
    legal_mode = LegalMode.SCRAPE
    priority = 24
    supported_api = None
    supports_pagination = False
    supports_incremental_sync = False
    supports_authentication = True  # would require login; part of why it's disabled
    supports_remote_filtering = True
    rate_limit_rps = 0.2

    async def search(self, target: CollectorTarget) -> list[RawJob]:
        raise ConfigurationError(_DISABLED_MESSAGE)

    def normalize(self, raw: RawJob) -> dict[str, Any]:
        raise ConfigurationError(_DISABLED_MESSAGE)

    def validate(self, raw: RawJob) -> bool:
        return False

    async def validate_configuration(self) -> HealthStatus:
        return HealthStatus(healthy=False, detail="disabled: interface stub, never runs")

    async def validate_connectivity(self) -> HealthStatus:
        return HealthStatus(healthy=False, detail="disabled: interface stub, never runs")
