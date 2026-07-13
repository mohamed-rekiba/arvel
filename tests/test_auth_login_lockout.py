"""Login throttling / lockout: LoginRateLimiter + AuthManager integration."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.auth import AuthManager
from arvel.auth.throttle import LoginRateLimiter
from arvel.cache import CacheManager
from arvel.security import Hasher


def _cache() -> Any:
    return CacheManager().driver("array")


# --- LoginRateLimiter ---------------------------------------------------------


@pytest.mark.asyncio
async def test_locks_after_max_attempts() -> None:
    limiter = LoginRateLimiter(_cache(), max_attempts=3, decay_seconds=60)
    assert await limiter.too_many_attempts("ada") is False
    for _ in range(3):
        await limiter.record_failure("ada")
    assert await limiter.too_many_attempts("ada") is True


@pytest.mark.asyncio
async def test_clear_resets_the_counter() -> None:
    limiter = LoginRateLimiter(_cache(), max_attempts=2, decay_seconds=60)
    await limiter.record_failure("ada")
    await limiter.record_failure("ada")
    assert await limiter.too_many_attempts("ada") is True
    await limiter.clear("ada")
    assert await limiter.too_many_attempts("ada") is False


@pytest.mark.asyncio
async def test_lockout_is_per_identifier() -> None:
    limiter = LoginRateLimiter(_cache(), max_attempts=2, decay_seconds=60)
    await limiter.record_failure("ada")
    await limiter.record_failure("ada")
    assert await limiter.too_many_attempts("ada") is True
    assert await limiter.too_many_attempts("bob") is False  # bob is unaffected


@pytest.mark.asyncio
async def test_available_in_counts_down_from_decay() -> None:
    limiter = LoginRateLimiter(_cache(), max_attempts=1, decay_seconds=300)
    assert await limiter.available_in("ada") == 0  # nothing recorded yet
    await limiter.record_failure("ada")
    remaining = await limiter.available_in("ada")
    assert 0 < remaining <= 300


@pytest.mark.asyncio
async def test_identifier_is_normalized_no_casing_evasion() -> None:
    """Casing/whitespace variants of the same login must share one bucket."""
    limiter = LoginRateLimiter(_cache(), max_attempts=2, decay_seconds=60)
    await limiter.record_failure("Ada@Example.com")
    await limiter.record_failure("  ada@example.com ")  # same account, different casing/spaces
    assert await limiter.too_many_attempts("ADA@EXAMPLE.COM") is True


@pytest.mark.asyncio
async def test_fail_open_vs_fail_closed_on_cache_error() -> None:
    """On a cache backend error, fail_open allows (default), fail_open=False denies."""

    class _BrokenCache:
        async def get(self, *a: Any, **k: Any) -> Any:
            raise RuntimeError("cache down")

    open_limiter = LoginRateLimiter(_BrokenCache(), max_attempts=3)
    assert await open_limiter.too_many_attempts("ada") is False  # fail open → not locked

    closed_limiter = LoginRateLimiter(_BrokenCache(), max_attempts=3, fail_open=False)
    assert await closed_limiter.too_many_attempts("ada") is True  # fail closed → locked


# --- AuthManager integration --------------------------------------------------


class _User:
    def __init__(self, password_hash: str) -> None:
        self.id = 1
        self.password = password_hash

    def get_auth_password(self) -> str:
        return self.password


@pytest.mark.asyncio
async def test_attempt_locks_out_after_repeated_failures() -> None:
    user = _User(Hasher().make("correct"))

    async def provider(_credentials: dict[str, Any]) -> Any:
        return user  # the user exists; only the password is wrong below

    auth = AuthManager(limiter=LoginRateLimiter(_cache(), max_attempts=3, decay_seconds=60))
    creds_bad = {"email": "ada@example.com", "password": "wrong"}

    for _ in range(3):
        assert await auth.attempt(creds_bad, provider) is False
    # now locked: even the CORRECT password is refused while locked out
    assert (
        await auth.attempt({"email": "ada@example.com", "password": "correct"}, provider) is False
    )


@pytest.mark.asyncio
async def test_successful_attempt_clears_lockout_counter() -> None:
    user = _User(Hasher().make("correct"))

    async def provider(_credentials: dict[str, Any]) -> Any:
        return user

    limiter = LoginRateLimiter(_cache(), max_attempts=3, decay_seconds=60)
    auth = AuthManager(limiter=limiter)

    await auth.attempt({"email": "ada@example.com", "password": "wrong"}, provider)
    await auth.attempt({"email": "ada@example.com", "password": "wrong"}, provider)
    # a correct login clears the counter…
    assert await auth.attempt({"email": "ada@example.com", "password": "correct"}, provider) is True
    assert await limiter.too_many_attempts("ada@example.com") is False
    auth.logout()


@pytest.mark.asyncio
async def test_attempt_without_limiter_is_unchanged() -> None:
    user = _User(Hasher().make("correct"))

    async def provider(_credentials: dict[str, Any]) -> Any:
        return user

    auth = AuthManager()  # no limiter → original behaviour, never locks
    for _ in range(10):
        assert (
            await auth.attempt({"email": "ada@example.com", "password": "wrong"}, provider) is False
        )
    assert await auth.attempt({"email": "ada@example.com", "password": "correct"}, provider) is True
    auth.logout()
