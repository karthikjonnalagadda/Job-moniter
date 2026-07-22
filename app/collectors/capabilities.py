"""Capability negotiation.

Instead of consumers reading ``supports_*`` booleans directly, a collector
advertises a ``CapabilitySet`` and callers *negotiate* — ask whether a feature is
available and get the whole set. This lets future collectors advertise optional
features dynamically (overriding ``advertise_capabilities``) without changing
callers.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from app.models.base import AppBaseModel

if TYPE_CHECKING:
    from app.collectors.base import BaseCollector


class Capability(StrEnum):
    PAGINATION = "pagination"
    INCREMENTAL_SYNC = "incremental_sync"
    AUTHENTICATION = "authentication"
    REMOTE_FILTERING = "remote_filtering"
    BULK_FETCH = "bulk_fetch"
    SALARY = "salary"
    POSTED_DATE = "posted_date"
    REMOTE = "remote"
    COMPANY_LOGO = "company_logo"
    JOB_DESCRIPTION = "job_description"
    INCREMENTAL_UPDATES = "incremental_updates"


class CapabilitySet(AppBaseModel):
    """An immutable-ish set of advertised capabilities."""

    capabilities: set[Capability]

    def supports(self, capability: Capability) -> bool:
        return capability in self.capabilities

    def negotiate(self, requested: set[Capability]) -> set[Capability]:
        """Return the subset of ``requested`` this collector actually supports."""

        return {c for c in requested if c in self.capabilities}


def advertise(collector: type[BaseCollector]) -> CapabilitySet:
    """Build the capability set a collector advertises (from its tag list)."""

    valid = {c.value for c in Capability}
    tags = {tag for tag in collector.capabilities() if tag in valid}
    return CapabilitySet(capabilities={Capability(tag) for tag in tags})
