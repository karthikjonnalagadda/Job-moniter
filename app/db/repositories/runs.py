"""Scheduler-run repository (durable run history).

Persists one ``SchedulerRun`` per daily execution so run history outlives the
ephemeral CI logs. Keyed on ``run_id``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.db.repositories.base import MongoRepository
from app.models.run import SchedulerRun

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

COLLECTION = "scheduler_logs"


class RunRepository(MongoRepository[SchedulerRun]):
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db, COLLECTION, SchedulerRun)

    async def get_by_run_id(self, run_id: str) -> SchedulerRun | None:
        return await self.find_one({"run_id": run_id})

    async def save(self, run: SchedulerRun) -> SchedulerRun:
        return await self.upsert({"run_id": run.run_id}, run)

    async def list_recent(self, *, limit: int = 20) -> list[SchedulerRun]:
        return await self.find({}, limit=limit, sort=[("started_at", -1)])
