"""Dead-letter repository."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.db.repositories.base import MongoRepository
from app.models.dead_letter import DeadLetter

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

COLLECTION = "dead_letters"


class DeadLetterRepository(MongoRepository[DeadLetter]):
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db, COLLECTION, DeadLetter)

    async def record(
        self,
        *,
        kind: str,
        source: str,
        reason: str,
        payload: dict[str, Any],
        error_code: str | None = None,
        import_id: str | None = None,
    ) -> DeadLetter:
        return await self.insert(
            DeadLetter(
                kind=kind,
                source=source,
                reason=reason,
                payload=payload,
                error_code=error_code,
                import_id=import_id,
            )
        )

    async def list_unreplayed(self, *, limit: int = 100) -> list[DeadLetter]:
        return await self.find({"replayed": False}, limit=limit, sort=[("created_at", -1)])

    async def mark_replayed(self, entity_id: str) -> DeadLetter | None:
        return await self.update(entity_id, {"replayed": True})
