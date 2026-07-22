"""Configuration repository (versioned runtime config).

Persists a single active ``AppConfigDocument`` per (user, key). ``save`` bumps
the ``version`` so updates are auditable and support future optimistic
concurrency. ``ConfigService`` reads through this repo and falls back to env.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.db.repositories.base import MongoRepository
from app.models.app_config import AppConfigDocument
from app.models.common import DEFAULT_USER_ID

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

COLLECTION = "app_config"


class ConfigRepository(MongoRepository[AppConfigDocument]):
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db, COLLECTION, AppConfigDocument)

    async def get_active(
        self,
        *,
        user_id: str = DEFAULT_USER_ID,
        key: str = "global",
    ) -> AppConfigDocument | None:
        return await self.find_one({"user_id": user_id, "key": key})

    async def save(self, config: AppConfigDocument) -> AppConfigDocument:
        """Upsert the config document, bumping its version on each save."""

        current = await self.get_active(user_id=config.user_id, key=config.key)
        config.version = (current.version + 1) if current else 1
        return await self.upsert({"user_id": config.user_id, "key": config.key}, config)
