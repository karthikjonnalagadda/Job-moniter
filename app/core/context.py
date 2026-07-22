"""Run + correlation context propagated across the whole pipeline.

Every unit of work — an inbound API request or a scheduled pipeline run — carries
two identifiers:

* ``run_id``         — identifies one pipeline execution (a daily run).
* ``correlation_id`` — identifies one causal chain of work; propagated across
  API → collectors → ranking → DB writes → email/export → logs.

They live in ``contextvars`` so any code (sync or async) can read the current
context without threading an argument through every function. The logging layer
injects both into every log record (see ``app.config.logging``), and the API
middleware sets/echoes ``correlation_id`` per request. Persistence and log
documents stamp these IDs so a single run is trivially traceable end to end.

Pure module: no I/O, no framework imports — safe for the domain layer.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass

# Sentinel shown when no context has been established yet.
UNSET = "-"

_run_id_var: ContextVar[str] = ContextVar("run_id", default=UNSET)
_correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default=UNSET)


def new_id(prefix: str = "") -> str:
    """Return a fresh short unique id, optionally namespaced (``run_``, ``req_``)."""

    token = uuid.uuid4().hex
    return f"{prefix}{token}" if prefix else token


@dataclass(frozen=True, slots=True)
class RunContext:
    """Immutable identifiers for one traceable unit of work."""

    run_id: str
    correlation_id: str

    @classmethod
    def new(cls, *, run_id: str | None = None, correlation_id: str | None = None) -> RunContext:
        return cls(
            run_id=run_id or new_id("run_"),
            correlation_id=correlation_id or new_id("cor_"),
        )


def current_run_id() -> str:
    return _run_id_var.get()


def current_correlation_id() -> str:
    return _correlation_id_var.get()


def current_context() -> RunContext:
    """Snapshot the ambient context (values may be ``UNSET``)."""

    return RunContext(run_id=_run_id_var.get(), correlation_id=_correlation_id_var.get())


@contextmanager
def use_context(ctx: RunContext) -> Iterator[RunContext]:
    """Bind ``ctx`` for the duration of the ``with`` block, then restore.

    Works for both sync and async call trees (contextvars are async-safe).
    """

    run_token: Token[str] = _run_id_var.set(ctx.run_id)
    cor_token: Token[str] = _correlation_id_var.set(ctx.correlation_id)
    try:
        yield ctx
    finally:
        _run_id_var.reset(run_token)
        _correlation_id_var.reset(cor_token)


def bind_correlation_id(correlation_id: str) -> Token[str]:
    """Set only the correlation id (used by API middleware). Caller resets."""

    return _correlation_id_var.set(correlation_id)


def reset_correlation_id(token: Token[str]) -> None:
    _correlation_id_var.reset(token)
