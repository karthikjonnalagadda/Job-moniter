"""Database bootstrap orchestration against an in-memory Mongo."""

from __future__ import annotations

from app.config.settings import Settings
from app.db.bootstrap import bootstrap_database
from app.db.repositories.config import ConfigRepository
from app.db.repositories.users import UserRepository


async def test_bootstrap_creates_indexes_and_seeds(mock_db) -> None:
    settings = Settings()
    result = await bootstrap_database(mock_db, settings, with_vector_index=True, seed=True)

    # indexes created (resilient path; mongomock supports basic create_index)
    assert result.indexes_created > 0
    # vector index is a no-op on mongomock — must not raise, returns False
    assert result.vector_index_requested is False
    assert result.default_user_ready is True
    assert result.default_config_ready is True

    # seed rows exist and are idempotent on re-run
    assert await UserRepository(mock_db).get_by_user_id() is not None
    assert await ConfigRepository(mock_db).get_active() is not None

    again = await bootstrap_database(mock_db, settings, seed=True)
    assert await UserRepository(mock_db).count() == 1
    assert again.default_config_ready is True
