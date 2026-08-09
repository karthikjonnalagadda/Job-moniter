"""Lever collection survives transient rate limits; blocked pages are not retried.

Drives the real ``LeverCollector`` through the shared ``RateLimitedHttpClient``
with an injected transport, proving:

* a 429 (Lever's rate-limit signal) and 5xx are retried with backoff and the
  collection then succeeds — the "add retry/backoff for occasional Lever rate
  limits/timeouts" requirement, handled once in the shared client;
* a 403 (blocked) is returned on the first attempt with no retry storm — the
  "do not aggressively retry blocked sites" requirement.
"""

from __future__ import annotations

import httpx
import pytest
from app.collectors.ats.lever import LeverCollector
from app.collectors.base import CollectorTarget
from app.config.settings import HttpSettings
from app.core.exceptions import CollectorError
from app.http.client import RateLimitedHttpClient
from app.http.retry import RetryPolicy

_LEVER_PAGE = [
    {
        "id": "1",
        "text": "Data Engineer",
        "hostedUrl": "https://jobs.lever.co/acme/1",
        "categories": {"location": "Bengaluru, India"},
        "createdAt": 1_700_000_000_000,
    }
]


class _SeqTransport:
    """Fake httpx client yielding a fixed response sequence (last one repeats)."""

    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = responses
        self.calls = 0

    async def request(self, method: str, url: str, **_: object) -> httpx.Response:
        idx = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        return self._responses[idx]

    async def aclose(self) -> None:
        return None


def _client(responses: list[httpx.Response]) -> tuple[RateLimitedHttpClient, _SeqTransport]:
    client = RateLimitedHttpClient(
        HttpSettings(),
        # zero backoff keeps the test instant; retry logic itself is unchanged.
        retry_policy=RetryPolicy(max_retries=3, backoff_base_seconds=0.0, jitter_ratio=0.0),
    )
    transport = _SeqTransport(responses)
    client._client = transport  # type: ignore[assignment]
    return client, transport


async def test_lever_retries_through_rate_limit() -> None:
    client, transport = _client(
        [
            httpx.Response(429),  # rate limited
            httpx.Response(503),  # transient server error
            httpx.Response(200, json=_LEVER_PAGE),  # recovers
        ]
    )
    jobs = await LeverCollector(client).search(CollectorTarget(board_token="acme"))
    assert len(jobs) == 1
    assert jobs[0].title == "Data Engineer"
    assert transport.calls == 3  # two retries, then success


async def test_blocked_page_is_not_retried() -> None:
    client, transport = _client([httpx.Response(403)])  # WAF / forbidden
    with pytest.raises(CollectorError):
        await LeverCollector(client).search(CollectorTarget(board_token="acme"))
    assert transport.calls == 1  # 403 is terminal — no retry storm
