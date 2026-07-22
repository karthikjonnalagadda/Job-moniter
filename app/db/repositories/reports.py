"""Report history repository."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.db.repositories.base import MongoRepository, Sort
from app.models.common import DEFAULT_USER_ID
from app.models.report_record import ReportRecord

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

COLLECTION = "report_history"


class ReportHistoryRepository(MongoRepository[ReportRecord]):
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db, COLLECTION, ReportRecord)

    async def get_by_report_id(self, report_id: str) -> ReportRecord | None:
        return await self.find_one({"report_id": report_id})

    async def list_recent(
        self, *, user_id: str = DEFAULT_USER_ID, limit: int = 50
    ) -> list[ReportRecord]:
        sort: Sort = [("generated_at", -1)]
        return await self.find({"user_id": user_id}, limit=limit, sort=sort)

    async def increment_download(self, report_id: str) -> ReportRecord | None:
        doc = await self.collection.find_one_and_update(
            {"report_id": report_id},
            {"$inc": {"download_count": 1}},
            return_document=True,
        )
        return self._to_model(doc)
