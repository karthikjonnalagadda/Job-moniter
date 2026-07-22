"""Shared pytest fixtures.

Uses ``mongomock_motor`` to provide an in-memory async Mongo, so tests need no
running database and no Atlas. The DI container is overridden to inject the fake
DB, exercising the real app wiring without external dependencies.
"""

from __future__ import annotations

import os

import pytest

# Force a hermetic, dependency-free config before settings are imported.
os.environ.setdefault("JOBAGENT_ENV", "development")
os.environ.setdefault("JOBAGENT_VECTOR__BACKEND", "numpy")
os.environ.setdefault("JOBAGENT_MONGO__URI", "mongodb://localhost:27017")
# Neutralise SMTP so tests NEVER hit a real mail server (a local .env may carry
# live credentials). Point at an unreachable port → notification sends fail fast
# and deterministically (the "no live external calls" rule).
os.environ.setdefault("JOBAGENT_SMTP__HOST", "localhost")
os.environ.setdefault("JOBAGENT_SMTP__PORT", "1")
os.environ.setdefault("JOBAGENT_SMTP__USERNAME", "")
os.environ.setdefault("JOBAGENT_SMTP__PASSWORD", "")


@pytest.fixture(autouse=True)
def _discover_collectors():
    """Ensure collector plugins are discovered before every test (idempotent)."""

    from app.collectors.loader import discover_collectors

    discover_collectors()


@pytest.fixture
def app_client(monkeypatch):
    """Return a TestClient with Mongo replaced by an in-memory fake."""

    from app.config.settings import get_settings
    from app.db import mongo as mongo_module
    from fastapi.testclient import TestClient
    from mongomock_motor import AsyncMongoMockClient

    # Patch the Motor client with an in-memory mock.
    def _fake_connect(self):  # type: ignore[no-untyped-def]
        self._client = AsyncMongoMockClient()
        self._db = self._client[self._settings.mongo.db_name]

    async def _connect(self):  # type: ignore[no-untyped-def]
        _fake_connect(self)

    monkeypatch.setattr(mongo_module.MongoClientManager, "connect", _connect)

    from app.main import create_app

    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as client:
        yield client


@pytest.fixture
def mock_db():
    """An in-memory async Mongo database for repository/integration tests."""

    from mongomock_motor import AsyncMongoMockClient

    client = AsyncMongoMockClient()
    return client["test_db"]
