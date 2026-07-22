"""Collector benchmark repository."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.db.repositories.base import MongoRepository
from app.models.collector_benchmark import CollectorBenchmark

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

COLLECTION = "collector_benchmarks"


class BenchmarkRepository(MongoRepository[CollectorBenchmark]):
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db, COLLECTION, CollectorBenchmark)

    async def get_for(self, collector: str) -> CollectorBenchmark | None:
        return await self.find_one({"collector": collector})

    async def record_run(
        self,
        collector: str,
        *,
        jobs_found: int,
        duplicates: int,
        errors: int,
        response_ms: float | None,
    ) -> CollectorBenchmark:
        """Atomically fold one run's results into the collector's rolling stats."""

        inc: dict[str, float | int] = {
            "runs": 1,
            "total_jobs_found": jobs_found,
            "total_duplicates": duplicates,
            "total_errors": errors,
        }
        if response_ms is not None:
            inc["total_response_ms"] = response_ms
            inc["response_samples"] = 1
        doc = await self.collection.find_one_and_update(
            {"collector": collector},
            {"$inc": inc, "$set": {"last_run_at": datetime.now(tz=UTC)}},
            upsert=True,
            return_document=True,
        )
        return CollectorBenchmark.model_validate(doc)

    async def list_all(self) -> list[CollectorBenchmark]:
        return await self.find({}, sort=[("collector", 1)])
