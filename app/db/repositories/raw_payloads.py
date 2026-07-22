"""Raw payload archive repository."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.db.repositories.base import MongoRepository
from app.models.raw_payload import RawPayload

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

COLLECTION = "raw_payloads"


class RawPayloadRepository(MongoRepository[RawPayload]):
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db, COLLECTION, RawPayload)

    async def archive(self, payload: RawPayload) -> RawPayload:
        return await self.insert(payload)

    async def latest_for(self, collector: str, *, limit: int = 20) -> list[RawPayload]:
        return await self.find({"collector": collector}, limit=limit, sort=[("created_at", -1)])
