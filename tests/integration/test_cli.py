"""Import/validate/list-collectors CLI entry points."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from app.importers.models import ImportOptions
from app.scripts import cli


@pytest.fixture
def _mongomock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the Mongo client used by CLI helpers with an in-memory mock."""

    from app.db import mongo as mongo_module
    from mongomock_motor import AsyncMongoMockClient

    async def fake_connect(self) -> None:  # type: ignore[no-untyped-def]
        self._client = AsyncMongoMockClient()
        self._db = self._client[self._settings.mongo.db_name]

    monkeypatch.setattr(mongo_module.MongoClientManager, "connect", fake_connect)


def test_list_collectors_cli(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["job-agent-list-collectors"])
    cli.list_collectors_main()
    data = json.loads(capsys.readouterr().out)
    assert any(c["name"] == "linkedin" for c in data)


async def test_validate_cli_helper(_mongomock, tmp_path: Path) -> None:
    path = tmp_path / "c.csv"
    path.write_text("company,slug\nAcme,acme\n", encoding="utf-8")
    assert await cli._validate(path, verbose=False) == 0

    bad = tmp_path / "bad.csv"
    bad.write_text("company,slug\nNoSlug,\n", encoding="utf-8")
    assert await cli._validate(bad, verbose=False) == 1  # invalid -> non-zero


async def test_import_cli_helper(
    _mongomock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "c.csv"
    path.write_text("company,slug,ats,ats_token\nAcme,acme,greenhouse,a\n", encoding="utf-8")
    rc = await cli._import(path, ImportOptions(), verbose=False)
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["stats"]["inserted"] == 1


async def test_sync_cli_helper(_mongomock, capsys: pytest.CaptureFixture[str]) -> None:
    assert await cli._sync(verbose=False) == 0
    summary = json.loads(capsys.readouterr().out)
    assert "routed" in summary
