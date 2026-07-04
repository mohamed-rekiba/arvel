"""HTTP (doc 13 §1) — Limit value object + cache-backed RateLimiter. Test-first."""

from __future__ import annotations

import pytest

from arvel.cache import CacheManager
from arvel.http.rate_limiter import Limit, RateLimiter


def _limiter() -> RateLimiter:
    return RateLimiter(CacheManager().driver("array"))


def test_limit_per_period_constructors_set_decay_seconds() -> None:
    assert (Limit.per_second(1).max_attempts, Limit.per_second(1).decay_seconds) == (1, 1)
    assert (Limit.per_minute(5).max_attempts, Limit.per_minute(5).decay_seconds) == (5, 60)
    assert Limit.per_hour(5).decay_seconds == 3600
    assert Limit.per_day(5).decay_seconds == 86400


def test_limit_by_sets_key_and_returns_self() -> None:
    limit = Limit.per_minute(10)
    assert limit.by("tenant-1") is limit
    assert limit.key == "tenant-1"


def test_limit_response_sets_callback_and_returns_self() -> None:
    limit = Limit.per_minute(10)
    cb = lambda request: {"custom": True}  # noqa: E731
    assert limit.response(cb) is limit
    assert limit.response_callback is cb


def test_for_registers_and_limiter_resolves() -> None:
    rl = _limiter()
    resolver = lambda request: Limit.per_minute(5)  # noqa: E731
    rl.for_("api", resolver)
    assert rl.limiter("api") is resolver
    assert rl.limiter("missing") is None


async def test_hit_increments_and_arms_decay() -> None:
    rl = _limiter()
    assert await rl.hit("k", decay_seconds=60) == 1
    assert await rl.hit("k", decay_seconds=60) == 2
    assert await rl.attempts("k") == 2


async def test_too_many_attempts_and_remaining() -> None:
    rl = _limiter()
    await rl.hit("k")
    await rl.hit("k")
    assert await rl.too_many_attempts("k", 2) is True
    assert await rl.too_many_attempts("k", 3) is False
    assert await rl.remaining("k", 3) == 1
    assert await rl.remaining("k", 2) == 0


async def test_available_in_reflects_ttl() -> None:
    rl = _limiter()
    assert await rl.available_in("never-hit") == 0
    await rl.hit("k", decay_seconds=30)
    ttl = await rl.available_in("k")
    assert 0 < ttl <= 30


async def test_clear_resets_the_counter() -> None:
    rl = _limiter()
    await rl.hit("k")
    await rl.clear("k")
    assert await rl.attempts("k") == 0


async def test_attempt_runs_callback_and_counts_it() -> None:
    rl = _limiter()
    calls = []

    async def work() -> str:
        calls.append(1)
        return "done"

    result = await rl.attempt("k", 2, work, decay_seconds=60)
    assert result == "done"
    assert calls == [1]
    assert await rl.attempts("k") == 1


async def test_attempt_returns_true_for_none_result() -> None:
    rl = _limiter()
    result = await rl.attempt("k", 2, lambda: None, decay_seconds=60)
    assert result is True


async def test_attempt_returns_false_and_skips_callback_when_over_limit() -> None:
    rl = _limiter()
    calls = []

    def work() -> str:
        calls.append(1)
        return "done"

    await rl.hit("k", decay_seconds=60)
    await rl.hit("k", decay_seconds=60)
    result = await rl.attempt("k", 2, work, decay_seconds=60)
    assert result is False
    assert calls == []  # never ran — already over the limit
    assert await rl.attempts("k") == 2  # not counted again


@pytest.mark.parametrize("period", ["second", "minute", "hour", "day"])
def test_all_periods_covered(period: str) -> None:
    from arvel.http.rate_limiter import _SECONDS

    assert period in _SECONDS
