"""Job repository.

Adds job-specific queries on top of the generic repository: dedup-aware upsert
by ``job_hash``, recent/ranked listings, and status transitions. All read
methods accept an optional ``user_id`` so multi-user scoping is a parameter, not
a rewrite (single-user default is ``DEFAULT_USER_ID``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.db.repositories.base import MongoRepository, Sort
from app.models.common import DEFAULT_USER_ID
from app.models.enums import JobStatus
from app.models.job import Job

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

COLLECTION = "jobs"


class JobRepository(MongoRepository[Job]):
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db, COLLECTION, Job)

    async def upsert_by_hash(self, job: Job) -> Job:
        """Insert or update a posting keyed on its dedup ``job_hash``."""

        return await self.upsert({"job_hash": job.job_hash}, job)

    async def exists_hash(self, job_hash: str) -> bool:
        return await self.count({"job_hash": job_hash}) > 0

    async def find_by_hashes(self, hashes: list[str]) -> dict[str, Job]:
        """Batch-fetch jobs by ``job_hash`` → ``{hash: Job}`` (order-independent)."""

        if not hashes:
            return {}
        jobs = await self.find({"job_hash": {"$in": hashes}}, limit=len(hashes))
        return {job.job_hash: job for job in jobs}

    async def iter_missing_embeddings(
        self, *, user_id: str = DEFAULT_USER_ID, limit: int = 100_000
    ) -> list[Job]:
        """Jobs that have no embedding yet (for incremental / migration passes)."""

        query: dict[str, Any] = {"user_id": user_id, "embedding": None}
        return await self.find(query, limit=limit)

    async def list_recent(
        self,
        *,
        user_id: str = DEFAULT_USER_ID,
        status: JobStatus | None = None,
        limit: int = 50,
    ) -> list[Job]:
        query: dict[str, Any] = {"user_id": user_id}
        if status is not None:
            query["status"] = status.value
        sort: Sort = [("posted_date", -1)]
        return await self.find(query, limit=limit, sort=sort)

    async def list_top_ranked(
        self,
        *,
        user_id: str = DEFAULT_USER_ID,
        min_score: float = 0.0,
        limit: int = 50,
    ) -> list[Job]:
        query: dict[str, Any] = {"user_id": user_id, "match.score": {"$gte": min_score}}
        return await self.find(query, limit=limit, sort=[("match.score", -1)])

    async def set_status(self, job_hash: str, status: JobStatus) -> Job | None:
        doc = await self.collection.find_one_and_update(
            {"job_hash": job_hash},
            {"$set": {"status": status.value}},
            return_document=True,
        )
        return self._to_model(doc)
