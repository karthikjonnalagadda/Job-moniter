"""Operational endpoints: benchmarks, import history, dead-letter queue.

Read-only views that feed dashboards and make debugging/replay easy.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import (
    BenchmarkRepositoryDep,
    DeadLetterRepositoryDep,
    ImportHistoryRepositoryDep,
    get_collector_states,
)
from app.collectors.state import CollectorStateInfo, CollectorStateRegistry
from app.models.collector_benchmark import CollectorBenchmark
from app.models.dead_letter import DeadLetter
from app.models.import_record import ImportRecord

router = APIRouter(tags=["ops"])


@router.get("/collector-states", response_model=list[CollectorStateInfo])
async def collector_states(
    states: Annotated[CollectorStateRegistry, Depends(get_collector_states)],
) -> list[CollectorStateInfo]:
    return states.all()


@router.get("/benchmarks", response_model=list[CollectorBenchmark])
async def collector_benchmarks(repo: BenchmarkRepositoryDep) -> list[CollectorBenchmark]:
    return await repo.list_all()


@router.get("/imports", response_model=list[ImportRecord])
async def import_history(repo: ImportHistoryRepositoryDep, limit: int = 20) -> list[ImportRecord]:
    return await repo.list_recent(limit=limit)


@router.get("/imports/{import_id}", response_model=ImportRecord)
async def import_record(import_id: str, repo: ImportHistoryRepositoryDep) -> ImportRecord:
    record = await repo.get_by_import_id(import_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Import '{import_id}' not found")
    return record


@router.get("/dead-letters", response_model=list[DeadLetter])
async def dead_letters(repo: DeadLetterRepositoryDep, limit: int = 100) -> list[DeadLetter]:
    return await repo.list_unreplayed(limit=limit)
