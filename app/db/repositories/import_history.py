"""Import history repository (import versioning)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.db.repositories.base import MongoRepository
from app.importers.records import ImportRecord

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

COLLECTION = "import_history"


class ImportHistoryRepository(MongoRepository[ImportRecord]):
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db, COLLECTION, ImportRecord)

    async def save(self, record: ImportRecord) -> ImportRecord:
        return await self.upsert({"import_id": record.import_id}, record)

    async def get_by_import_id(self, import_id: str) -> ImportRecord | None:
        return await self.find_one({"import_id": import_id})

    async def list_recent(self, *, limit: int = 20) -> list[ImportRecord]:
        return await self.find({}, limit=limit, sort=[("started_at", -1)])
