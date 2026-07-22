"""Resume-embedding repository (``resume_embeddings`` collection).

Keyed by ``(user_id, resume_id)`` so each resume version has exactly one stored
embedding, upserted in place when the resume text changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.db.repositories.base import MongoRepository
from app.models.common import DEFAULT_USER_ID
from app.models.resume import ResumeEmbedding

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

COLLECTION = "resume_embeddings"


class ResumeEmbeddingRepository(MongoRepository[ResumeEmbedding]):
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db, COLLECTION, ResumeEmbedding)

    async def get_by_resume_id(
        self, resume_id: str, *, user_id: str = DEFAULT_USER_ID
    ) -> ResumeEmbedding | None:
        return await self.find_one({"resume_id": resume_id, "user_id": user_id})

    async def upsert_resume(self, resume: ResumeEmbedding) -> ResumeEmbedding:
        return await self.upsert(
            {"resume_id": resume.resume_id, "user_id": resume.user_id}, resume
        )

    async def list_for_user(self, *, user_id: str = DEFAULT_USER_ID) -> list[ResumeEmbedding]:
        return await self.find({"user_id": user_id}, limit=1000)
