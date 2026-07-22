"""Collector state machine + registry."""

from __future__ import annotations

import pytest
from app.collectors.state import (
    CollectorState,
    CollectorStateMachine,
    CollectorStateRegistry,
    InvalidTransition,
)


def test_valid_lifecycle() -> None:
    machine = CollectorStateMachine("greenhouse")
    assert machine.state is CollectorState.IDLE
    machine.transition(CollectorState.SYNCING)
    machine.transition(CollectorState.RATE_LIMITED)
    machine.transition(CollectorState.SYNCING)
    machine.transition(CollectorState.IDLE)


def test_invalid_transition_rejected() -> None:
    machine = CollectorStateMachine("greenhouse")
    # IDLE -> RATE_LIMITED is not allowed
    with pytest.raises(InvalidTransition):
        machine.transition(CollectorState.RATE_LIMITED)


def test_registry_tracks_states() -> None:
    registry = CollectorStateRegistry()
    registry.get("greenhouse").transition(CollectorState.SYNCING)
    registry.get("lever")  # created idle
    infos = {i.collector: i.state for i in registry.all()}
    # CollectorStateInfo stores enum *values* (use_enum_values) -> compare with ==
    assert infos["greenhouse"] == CollectorState.SYNCING
    assert infos["lever"] == CollectorState.IDLE
