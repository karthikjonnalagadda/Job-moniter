"""MongoDB Atlas connection lifecycle (async, via Motor).

Exposes a small ``MongoClientManager`` that owns the ``AsyncIOMotorClient`` and
its database handle. The client is created at application startup and closed at
shutdown (see ``app.main`` lifespan). Repositories receive the database handle
through dependency injection — they never construct their own client.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config.logging import get_logger

if TYPE_CHECKING:
    from app.config.settings import Settings

log = get_logger("api")


class MongoClientManager:
    """Owns the lifecycle of a single Motor client for the process."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: AsyncIOMotorClient | None = None
        self._db: AsyncIOMotorDatabase | None = None

    async def connect(self) -> None:
        if self._client is not None:
            return
        mongo = self._settings.mongo
        self._client = AsyncIOMotorClient(
            mongo.uri.get_secret_value(),
            maxPoolSize=mongo.max_pool_size,
            serverSelectionTimeoutMS=mongo.server_selection_timeout_ms,
            uuidRepresentation="standard",
            tz_aware=True,
        )
        self._db = self._client[mongo.db_name]
        log.info("Mongo client initialised (db={})", mongo.db_name)

    async def disconnect(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
            self._db = None
            log.info("Mongo client closed")

    @property
    def db(self) -> AsyncIOMotorDatabase:
        if self._db is None:
            raise RuntimeError("Mongo client not connected. Call connect() first.")
        return self._db

    async def ping(self) -> bool:
        """Return True if the server responds to a ``ping`` command."""

        if self._client is None:
            return False
        try:
            await self._client.admin.command("ping")
            return True
        except Exception as exc:  # health check must never raise
            log.warning("Mongo ping failed: {}", exc)
            return False
