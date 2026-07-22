"""Greenhouse / Lever / Ashby collectors (fixture payloads, no live calls)."""

from __future__ import annotations

import httpx
import pytest
from app.collectors.ats.ashby import AshbyCollector
from app.collectors.ats.greenhouse import GreenhouseCollector
from app.collectors.ats.lever import LeverCollector
from app.collectors.base import CollectorTarget

from tests.http_fakes import (
    ASHBY_JOBS,
    GREENHOUSE_JOBS,
    LEVER_PAGE_0,
    LEVER_PAGE_1,
    FakeHttpClient,
)

TARGET = CollectorTarget(board_token="acme", company_name="Acme")


async def test_greenhouse_parses_and_validates() -> None:
    def handler(method: str, url: str, **_: object) -> httpx.Response:
        return httpx.Response(200, json=GREENHOUSE_JOBS, headers={"etag": "gh-v1"})

    collector = GreenhouseCollector(FakeHttpClient(handler))
    jobs = await collector.search(TARGET)

    assert len(jobs) == 1  # the empty-title row was dropped
    job = jobs[0]
    assert job.external_id == "123"
    assert job.title == "Backend Engineer"
    assert job.company == "Acme"
    assert job.url.endswith("/123")
    assert job.location == "Remote"
    assert job.posted_at is not None
    # captured watermark for the next incremental run
    assert collector.sync_watermark()["etag"] == "gh-v1"


async def test_greenhouse_incremental_304_returns_empty() -> None:
    seen: dict[str, str] = {}

    def handler(method: str, url: str, **kwargs: object) -> httpx.Response:
        headers = kwargs.get("headers") or {}
        seen.update(headers)  # type: ignore[arg-type]
        return httpx.Response(304)

    collector = GreenhouseCollector(FakeHttpClient(handler))
    target = CollectorTarget(board_token="acme", extra={"etag": "gh-v1"})
    jobs = await collector.search(target)

    assert jobs == []
    assert seen.get("If-None-Match") == "gh-v1"  # conditional header sent


async def test_lever_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.collectors.ats.lever._PAGE_LIMIT", 2)

    def handler(method: str, url: str, **_: object) -> httpx.Response:
        page = LEVER_PAGE_0 if "offset=0" in url else LEVER_PAGE_1
        return httpx.Response(200, json=page)

    collector = LeverCollector(FakeHttpClient(handler))
    jobs = await collector.search(TARGET)

    assert [j.external_id for j in jobs] == ["a1", "a2", "a3"]  # both pages aggregated
    assert jobs[0].url.startswith("https://jobs.lever.co")


async def test_ashby_posts_and_parses() -> None:
    def handler(method: str, url: str, **_: object) -> httpx.Response:
        assert method == "POST"
        return httpx.Response(200, json=ASHBY_JOBS)

    collector = AshbyCollector(FakeHttpClient(handler))
    jobs = await collector.search(TARGET)

    assert len(jobs) == 1
    assert jobs[0].external_id == "x1"
    assert jobs[0].title == "ML Engineer"
    assert collector.supports_salary is True  # includeCompensation


async def test_collector_health_probe() -> None:
    def handler(method: str, url: str, **_: object) -> httpx.Response:
        return httpx.Response(200, json={"jobs": []})

    collector = GreenhouseCollector(FakeHttpClient(handler))
    report = await collector.health_check()
    assert report.healthy is True
    assert report.connectivity.healthy is True


async def test_collector_without_http_fails_cleanly() -> None:
    from app.core.exceptions import ConfigurationError

    collector = GreenhouseCollector()  # no http bound
    with pytest.raises(ConfigurationError):
        await collector.search(TARGET)
