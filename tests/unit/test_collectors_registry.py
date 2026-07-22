"""Registry + LinkedIn interface-stub guarantees (Phase 2)."""

from __future__ import annotations

import pytest
from app.collectors import available_collectors, get_collector_class
from app.collectors.base import CollectorTarget
from app.core.exceptions import ConfigurationError
from app.models.enums import LegalMode, SourceType


def test_linkedin_is_registered_but_disabled() -> None:
    registry = available_collectors()
    assert "linkedin" in registry, "LinkedIn must exist as a registered plugin"

    cls = get_collector_class("linkedin")
    assert cls.source_type is SourceType.JOB_BOARD
    assert cls.legal_mode is LegalMode.SCRAPE  # opt-in only, never default-on


async def test_linkedin_refuses_to_run() -> None:
    collector = get_collector_class("linkedin")()

    # Non-functional by design: search must never collect anything.
    with pytest.raises(ConfigurationError):
        await collector.search(CollectorTarget(company_name="anything"))

    # And it always reports unhealthy so orchestration skips it.
    health = await collector.health_check()
    assert health.healthy is False
