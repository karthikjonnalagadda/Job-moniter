"""Correlation/run context propagation."""

from __future__ import annotations

from app.core.context import (
    UNSET,
    RunContext,
    current_correlation_id,
    current_run_id,
    use_context,
)


def test_defaults_are_unset() -> None:
    assert current_run_id() == UNSET
    assert current_correlation_id() == UNSET


def test_use_context_binds_and_restores() -> None:
    ctx = RunContext.new()
    assert ctx.run_id.startswith("run_")
    assert ctx.correlation_id.startswith("cor_")

    with use_context(ctx):
        assert current_run_id() == ctx.run_id
        assert current_correlation_id() == ctx.correlation_id

    # restored after the block
    assert current_run_id() == UNSET


def test_explicit_ids_preserved() -> None:
    ctx = RunContext.new(run_id="run_x", correlation_id="cor_y")
    with use_context(ctx):
        assert current_run_id() == "run_x"
        assert current_correlation_id() == "cor_y"
