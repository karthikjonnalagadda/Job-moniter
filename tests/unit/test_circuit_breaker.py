"""Circuit breaker state machine + HTTP client integration."""

from __future__ import annotations

import httpx
import pytest
from app.config.settings import HttpSettings
from app.core.exceptions import CircuitOpenError, RateLimitError
from app.http.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState
from app.http.client import RateLimitedHttpClient
from app.http.retry import RetryPolicy


def test_opens_after_threshold_then_half_open_then_closes() -> None:
    clock = {"t": 0.0}
    cb = CircuitBreaker(
        CircuitBreakerConfig(failure_threshold=3, reset_timeout=10, half_open_max_calls=1),
        monotonic=lambda: clock["t"],
    )
    assert cb.state is CircuitState.CLOSED
    for _ in range(3):
        cb.record_failure()
    assert cb.state is CircuitState.OPEN
    assert cb.allow() is False

    clock["t"] = 11  # past reset_timeout
    assert cb.state is CircuitState.HALF_OPEN
    assert cb.allow() is True  # one trial call permitted
    assert cb.allow() is False  # trials exhausted
    cb.record_success()
    assert cb.state is CircuitState.CLOSED


def test_half_open_failure_reopens() -> None:
    clock = {"t": 0.0}
    cb = CircuitBreaker(
        CircuitBreakerConfig(failure_threshold=1, reset_timeout=5),
        monotonic=lambda: clock["t"],
    )
    cb.record_failure()  # opens
    clock["t"] = 6
    assert cb.state is CircuitState.HALF_OPEN
    assert cb.allow() is True
    cb.record_failure()  # trial failed -> reopen
    assert cb.state is CircuitState.OPEN


async def test_client_circuit_opens_after_failures() -> None:
    client = RateLimitedHttpClient(
        HttpSettings(),
        retry_policy=RetryPolicy(max_retries=0),
        breaker_config=CircuitBreakerConfig(failure_threshold=2, reset_timeout=100),
    )

    class _FailingClient:
        async def request(self, *_a: object, **_k: object) -> httpx.Response:
            raise httpx.ConnectError("boom")

        async def aclose(self) -> None:
            return None

    client._client = _FailingClient()  # type: ignore[assignment]

    for _ in range(2):
        with pytest.raises(RateLimitError):
            await client.request("GET", "http://x.example/jobs")

    # threshold reached -> fail fast
    with pytest.raises(CircuitOpenError):
        await client.request("GET", "http://x.example/jobs")


def test_configure_host_creates_per_host_limiter() -> None:
    client = RateLimitedHttpClient(HttpSettings())
    client.configure_host("api.greenhouse.io", rps=5, burst=5, max_concurrency=2)
    assert client.circuit_state("https://api.greenhouse.io/v1/boards") == "closed"
    # unknown host uses the default limiter (also closed initially)
    assert client.circuit_state("https://other.example/") == "closed"
