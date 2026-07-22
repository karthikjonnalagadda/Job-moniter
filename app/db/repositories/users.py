"""User repository (auth-ready; auth not implemented).

Keyed on the stable ``user_id`` business key. In single-user mode only the
``default`` user exists; ``ensure_default`` idempotently creates it so the app is
fully functional without any login flow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.db.repositories.base import MongoRepository
from app.models.common import DEFAULT_USER_ID
from app.models.user import User

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

COLLECTION = "users"


class UserRepository(MongoRepository[User]):
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db, COLLECTION, User)

    async def get_by_user_id(self, user_id: str = DEFAULT_USER_ID) -> User | None:
        return await self.find_one({"user_id": user_id})

    async def ensure_default(self, email: str) -> User:
        """Create the single default user if absent; return it either way."""

        existing = await self.get_by_user_id(DEFAULT_USER_ID)
        if existing is not None:
            return existing
        return await self.upsert(
            {"user_id": DEFAULT_USER_ID},
            User(user_id=DEFAULT_USER_ID, email=email),
        )
