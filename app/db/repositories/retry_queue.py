"""Retry-queue repository."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from app.db.repositories.base import MongoRepository
from app.models.retry_task import RetryStatus, RetryTask

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

COLLECTION = "retry_queue"


class RetryQueueRepository(MongoRepository[RetryTask]):
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db, COLLECTION, RetryTask)

    async def upsert_task(self, task: RetryTask) -> RetryTask:
        return await self.upsert({"task_id": task.task_id}, task)

    async def due(self, *, now: datetime, limit: int = 50) -> list[RetryTask]:
        query = {
            "status": RetryStatus.PENDING.value,
            "next_attempt_at": {"$lte": now},
        }
        return await self.find(query, limit=limit, sort=[("next_attempt_at", 1)])

    async def count_pending(self) -> int:
        return await self.count({"status": RetryStatus.PENDING.value})

    async def set_status(self, task_id: str, status: RetryStatus) -> RetryTask | None:
        doc = await self.collection.find_one_and_update(
            {"task_id": task_id},
            {"$set": {"status": status.value}},
            return_document=True,
        )
        return self._to_model(doc)
