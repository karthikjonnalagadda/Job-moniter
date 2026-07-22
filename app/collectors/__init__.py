"""app.collectors package.

Collector plugins are **auto-discovered** — call ``discover_collectors()`` (done
at app startup) to import every module under ``ats`` / ``career_sites`` /
``job_boards`` and populate the registry via their ``@register`` decorators.
There is no manual registration list. Phase 4 ships only the LinkedIn interface
stub (registered but disabled); real collectors are added in Phases 5-7 by
dropping a module into one of those packages.
"""

from app.collectors.base import CollectorHealthReport, CollectorMetadata
from app.collectors.registry import (
    available_collectors,
    describe_all,
    get_collector_class,
    register,
)

__all__ = [
    "CollectorHealthReport",
    "CollectorMetadata",
    "available_collectors",
    "describe_all",
    "get_collector_class",
    "register",
]
