"""User-preferences repository (per-user, resume versioning).

One document per ``user_id``. Provides resume-version management and stores the
active version's ``resume_embedding`` used by the ranking query.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.db.repositories.base import MongoRepository
from app.models.common import DEFAULT_USER_ID
from app.models.user_preferences import ResumeVersion, UserPreferences

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

COLLECTION = "user_preferences"


class UserPreferencesRepository(MongoRepository[UserPreferences]):
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db, COLLECTION, UserPreferences)

    async def get_for_user(self, user_id: str = DEFAULT_USER_ID) -> UserPreferences | None:
        return await self.find_one({"user_id": user_id})

    async def ensure_for_user(self, user_id: str = DEFAULT_USER_ID) -> UserPreferences:
        existing = await self.get_for_user(user_id)
        if existing is not None:
            return existing
        return await self.upsert({"user_id": user_id}, UserPreferences(user_id=user_id))

    async def add_resume_version(
        self,
        version: ResumeVersion,
        *,
        user_id: str = DEFAULT_USER_ID,
        make_active: bool = False,
    ) -> UserPreferences:
        """Append (or replace) a resume version, optionally activating it."""

        prefs = await self.ensure_for_user(user_id)
        prefs.resume_versions = [
            v for v in prefs.resume_versions if v.version_id != version.version_id
        ]
        version.is_active = make_active
        prefs.resume_versions.append(version)
        if make_active:
            for v in prefs.resume_versions:
                v.is_active = v.version_id == version.version_id
            prefs.active_resume_id = version.version_id
            prefs.resume_embedding = version.embedding
        return await self.upsert({"user_id": user_id}, prefs)
