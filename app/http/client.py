"""Shared HTTP client port + rate-limited implementation.

Every collector obtains its network access through this one client. It provides,
in a single place, what would otherwise be re-implemented per collector:

* **rate limiting**       — async token bucket at ``default_rate_limit_rps``.
* **request queue**       — a concurrency semaphore bounds in-flight requests.
* **retries + backoff**   — capped exponential backoff with jitter on transient
  errors (network failures and configurable retry statuses).
* **timeout handling**    — a default httpx timeout on every request.
* **custom user agent**   — set once from settings.

Collectors depend on the ``HttpClient`` port; ``RateLimitedHttpClient`` is the
default adapter. The client lazily creates its ``httpx.AsyncClient`` and must be
closed via ``aclose()`` (wired into the app lifespan).
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx

from app.config.logging import get_logger
from app.core.exceptions import CircuitOpenError, RateLimitError
from app.http.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from app.http.rate_limiter import AsyncTokenBucket
from app.http.retry import RetryPolicy

if TYPE_CHECKING:
    from app.config.settings import HttpSettings
    from app.metrics.base import MetricsSink

log = get_logger("collectors")


class _HostLimiter:
    """Per-host rate bucket + concurrency semaphore + circuit breaker."""

    def __init__(
        self,
        rps: float,
        burst: int,
        max_concurrency: int,
        breaker_cfg: CircuitBreakerConfig,
    ) -> None:
        self.bucket = AsyncTokenBucket(rps, capacity=burst)
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.breaker = CircuitBreaker(breaker_cfg)


class HttpClient(ABC):
    """Abstraction over 'make an HTTP request with resilience built in'."""

    @abstractmethod
    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Perform a resilient request and return the response."""

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    @abstractmethod
    async def aclose(self) -> None:
        """Release underlying connections."""


class RateLimitedHttpClient(HttpClient):
    """Default adapter: httpx + token-bucket rate limiting + retry/backoff."""

    def __init__(
        self,
        settings: HttpSettings,
        *,
        retry_policy: RetryPolicy | None = None,
        metrics: MetricsSink | None = None,
        max_concurrency: int = 10,
        breaker_config: CircuitBreakerConfig | None = None,
    ) -> None:
        self._settings = settings
        self._retry = retry_policy or RetryPolicy(max_retries=settings.max_retries)
        self._metrics = metrics
        self._breaker_config = breaker_config or CircuitBreakerConfig()
        self._default_limiter = _HostLimiter(
            settings.default_rate_limit_rps,
            burst=max(1, int(settings.default_rate_limit_rps)),
            max_concurrency=max_concurrency,
            breaker_cfg=self._breaker_config,
        )
        self._host_limiters: dict[str, _HostLimiter] = {}
        self._client: httpx.AsyncClient | None = None

    def configure_host(
        self, host: str, *, rps: float, burst: int, max_concurrency: int
    ) -> None:
        """Set per-host rate/concurrency limits (from a source's ConcurrencyLimits)."""

        self._host_limiters[host] = _HostLimiter(
            rps, burst=burst, max_concurrency=max_concurrency, breaker_cfg=self._breaker_config
        )

    def _limiter_for(self, url: str) -> _HostLimiter:
        host = urlparse(url).netloc
        return self._host_limiters.get(host, self._default_limiter)

    def circuit_state(self, url: str) -> str:
        return str(self._limiter_for(url).breaker.state)

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._settings.timeout_seconds,
                headers={"User-Agent": self._settings.user_agent},
                follow_redirects=True,
            )
        return self._client

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        client = self._ensure_client()
        limiter = self._limiter_for(url)
        last_exc: Exception | None = None

        for attempt in range(self._retry.max_retries + 1):
            if not limiter.breaker.allow():
                raise CircuitOpenError(
                    f"Circuit open for {urlparse(url).netloc}; failing fast",
                    details={"url": url},
                )
            # request queue (bounded concurrency) then per-host rate limit
            async with limiter.semaphore:
                await limiter.bucket.acquire()
                try:
                    response = await client.request(method, url, **kwargs)
                except httpx.HTTPError as exc:  # network/timeout errors are retryable
                    last_exc = exc
                    limiter.breaker.record_failure()
                    log.warning("HTTP {} {} failed (attempt {}): {}", method, url, attempt, exc)
                else:
                    if not self._retry.should_retry_status(response.status_code):
                        limiter.breaker.record_success()
                        return response
                    limiter.breaker.record_failure()
                    last_exc = None
                    log.warning(
                        "HTTP {} {} -> {} (attempt {}), will retry",
                        method,
                        url,
                        response.status_code,
                        attempt,
                    )
                    if attempt == self._retry.max_retries:
                        return response  # give the caller the last response to inspect

            if attempt < self._retry.max_retries:
                await asyncio.sleep(self._retry.backoff_for(attempt))

        raise RateLimitError(
            f"HTTP {method} {url} exhausted {self._retry.max_retries} retries",
            details={"error": str(last_exc) if last_exc else "retryable status"},
        )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
