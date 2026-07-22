"""Token-bucket rate limiter + retry policy."""

from __future__ import annotations

from app.http.rate_limiter import AsyncTokenBucket
from app.http.retry import RetryPolicy


async def test_bucket_allows_burst_up_to_capacity() -> None:
    bucket = AsyncTokenBucket(rate=1000, capacity=3)
    # three immediate acquisitions within the burst capacity should not block
    for _ in range(3):
        await bucket.acquire()


async def test_disabled_when_rate_zero() -> None:
    bucket = AsyncTokenBucket(rate=0)
    await bucket.acquire(tokens=100)  # no-op, returns immediately


def test_retry_policy_backoff_grows_and_caps() -> None:
    policy = RetryPolicy(
        max_retries=5, backoff_base_seconds=1.0, backoff_max_seconds=8.0, jitter_ratio=0
    )
    assert policy.backoff_for(0) == 1.0
    assert policy.backoff_for(1) == 2.0
    assert policy.backoff_for(2) == 4.0
    assert policy.backoff_for(10) == 8.0  # capped


def test_retry_policy_status_predicate() -> None:
    policy = RetryPolicy()
    assert policy.should_retry_status(503) is True
    assert policy.should_retry_status(200) is False
