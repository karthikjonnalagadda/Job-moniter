"""Collector benchmark repository + derived rates."""

from __future__ import annotations

from app.db.repositories.benchmarks import BenchmarkRepository


async def test_record_run_accumulates_and_computes_rates(mock_db) -> None:
    repo = BenchmarkRepository(mock_db)
    await repo.record_run("greenhouse", jobs_found=10, duplicates=2, errors=0, response_ms=100)
    benchmark = await repo.record_run(
        "greenhouse", jobs_found=6, duplicates=1, errors=1, response_ms=200
    )

    assert benchmark.runs == 2
    assert benchmark.total_jobs_found == 16
    assert benchmark.average_response_ms == 150.0
    assert benchmark.error_rate == 0.5
    assert benchmark.success_rate == 0.5
    assert benchmark.jobs_per_run == 8.0
    assert round(benchmark.duplicate_rate, 4) == round(3 / 16, 4)


async def test_get_for_and_list_all(mock_db) -> None:
    repo = BenchmarkRepository(mock_db)
    await repo.record_run("lever", jobs_found=5, duplicates=0, errors=0, response_ms=None)
    assert await repo.get_for("lever") is not None
    assert await repo.get_for("missing") is None
    assert len(await repo.list_all()) == 1
