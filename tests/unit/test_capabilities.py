"""Capability negotiation."""

from __future__ import annotations

from app.collectors.ats.greenhouse import GreenhouseCollector
from app.collectors.capabilities import Capability, CapabilitySet, advertise


def test_capability_set_supports_and_negotiate() -> None:
    caps = CapabilitySet(capabilities={Capability.PAGINATION, Capability.SALARY})
    assert caps.supports(Capability.PAGINATION)
    assert not caps.supports(Capability.REMOTE)
    negotiated = caps.negotiate({Capability.SALARY, Capability.REMOTE})
    assert negotiated == {Capability.SALARY}


def test_advertise_from_collector() -> None:
    caps = advertise(GreenhouseCollector)
    assert caps.supports(Capability.INCREMENTAL_SYNC)
    assert caps.supports(Capability.JOB_DESCRIPTION)
    assert caps.supports(Capability.BULK_FETCH)
    assert not caps.supports(Capability.SALARY)  # greenhouse doesn't advertise salary
