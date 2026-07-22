"""Pipeline run history repository."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.db.repositories.base import MongoRepository, Sort
from app.models.common import DEFAULT_USER_ID
from app.models.pipeline_run import PipelineRun

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

COLLECTION = "pipeline_runs"


class PipelineRunRepository(MongoRepository[PipelineRun]):
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db, COLLECTION, PipelineRun)

    async def get_by_run_id(self, run_id: str) -> PipelineRun | None:
        return await self.find_one({"run_id": run_id})

    async def list_recent(
        self, *, user_id: str = DEFAULT_USER_ID, limit: int = 50
    ) -> list[PipelineRun]:
        sort: Sort = [("started_at", -1)]
        return await self.find({"user_id": user_id}, limit=limit, sort=sort)
