"""Collector lifecycle state machine.

Tracks each collector's operational state and enforces valid transitions. The
executor drives transitions during a run; the API exposes the current state
(``GET /collectors/{name}/state``). State is process-local (in-memory) — durable
run history already lives in benchmarks / scheduler logs.

States:
    IDLE          — registered, not currently running.
    SYNCING       — a run is in progress.
    RATE_LIMITED  — throttled by rate limits (transient).
    BACKOFF       — waiting out a backoff after failure(s).
    FAILED        — last run failed.
    DISABLED      — administratively off (or a disabled source).
"""

from __future__ import annotations

from enum import StrEnum

from app.models.base import AppBaseModel


class CollectorState(StrEnum):
    IDLE = "idle"
    SYNCING = "syncing"
    RATE_LIMITED = "rate_limited"
    BACKOFF = "backoff"
    FAILED = "failed"
    DISABLED = "disabled"


# Allowed transitions (target set per source state).
_TRANSITIONS: dict[CollectorState, set[CollectorState]] = {
    CollectorState.IDLE: {CollectorState.SYNCING, CollectorState.DISABLED},
    CollectorState.SYNCING: {
        CollectorState.IDLE,
        CollectorState.RATE_LIMITED,
        CollectorState.BACKOFF,
        CollectorState.FAILED,
        CollectorState.DISABLED,
    },
    CollectorState.RATE_LIMITED: {
        CollectorState.SYNCING,
        CollectorState.BACKOFF,
        CollectorState.IDLE,
        CollectorState.DISABLED,
    },
    CollectorState.BACKOFF: {
        CollectorState.SYNCING,
        CollectorState.IDLE,
        CollectorState.FAILED,
        CollectorState.DISABLED,
    },
    CollectorState.FAILED: {
        CollectorState.SYNCING,
        CollectorState.BACKOFF,
        CollectorState.IDLE,
        CollectorState.DISABLED,
    },
    CollectorState.DISABLED: {CollectorState.IDLE},
}


class InvalidTransition(RuntimeError):
    pass


class CollectorStateInfo(AppBaseModel):
    collector: str
    state: CollectorState
    detail: str = ""


class CollectorStateMachine:
    """Per-collector state with transition validation."""

    def __init__(self, collector: str, initial: CollectorState = CollectorState.IDLE) -> None:
        self.collector = collector
        self._state = initial
        self.detail = ""

    @property
    def state(self) -> CollectorState:
        return self._state

    def can_transition(self, target: CollectorState) -> bool:
        return target == self._state or target in _TRANSITIONS[self._state]

    def transition(self, target: CollectorState, detail: str = "") -> None:
        if not self.can_transition(target):
            raise InvalidTransition(f"{self.collector}: {self._state} -> {target} not allowed")
        self._state = target
        self.detail = detail

    def info(self) -> CollectorStateInfo:
        return CollectorStateInfo(collector=self.collector, state=self._state, detail=self.detail)


class CollectorStateRegistry:
    """Process-wide registry of collector state machines."""

    def __init__(self) -> None:
        self._machines: dict[str, CollectorStateMachine] = {}

    def get(self, collector: str) -> CollectorStateMachine:
        if collector not in self._machines:
            self._machines[collector] = CollectorStateMachine(collector)
        return self._machines[collector]

    def all(self) -> list[CollectorStateInfo]:
        return [machine.info() for machine in self._machines.values()]
