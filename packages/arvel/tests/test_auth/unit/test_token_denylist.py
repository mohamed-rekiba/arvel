"""Token revocation denylist."""

from __future__ import annotations

import time

import pytest
from arvel.auth.token_denylist import (
    deny_token,
    is_revoked,
    is_token_denied,
    revoke_all_for_user,
    revoked_before_for_user,
)
from arvel.facades.cache import Cache


@pytest.mark.asyncio
async def test_deny_token_marks_jti_denied() -> None:
    with Cache.fake():
        assert await is_token_denied("abc") is False
        await deny_token("abc", expires_at_epoch=int(time.time()) + 900)
        assert await is_token_denied("abc") is True


@pytest.mark.asyncio
async def test_already_expired_token_is_still_denyable_for_one_second() -> None:
    # ttl is clamped to >= 1 so the put doesn't error on an expired token.
    with Cache.fake():
        await deny_token("stale", expires_at_epoch=int(time.time()) - 10)
        assert await is_token_denied("stale") is True


@pytest.mark.asyncio
async def test_empty_jti_is_never_denied() -> None:
    with Cache.fake():
        await deny_token("", expires_at_epoch=int(time.time()) + 900)
        assert await is_token_denied("") is False


@pytest.mark.asyncio
async def test_revoke_all_sets_user_cutoff() -> None:
    with Cache.fake():
        assert await revoked_before_for_user("7") is None
        before = int(time.time())
        await revoke_all_for_user("7", ttl_seconds=900)
        cutoff = await revoked_before_for_user("7")
        assert cutoff is not None
        assert cutoff >= before


@pytest.mark.asyncio
async def test_is_revoked_by_jti() -> None:
    with Cache.fake():
        await deny_token("jti-1", expires_at_epoch=int(time.time()) + 900)
        assert await is_revoked(jti="jti-1", subject="7", issued_at=int(time.time())) is True


@pytest.mark.asyncio
async def test_is_revoked_by_user_cutoff_for_old_token() -> None:
    with Cache.fake():
        old_iat = int(time.time()) - 60
        await revoke_all_for_user("7", ttl_seconds=900)
        # Token issued before the cutoff is revoked...
        assert await is_revoked(jti="x", subject="7", issued_at=old_iat) is True
        # ...but a token issued after the cutoff is fine.
        future_iat = int(time.time()) + 60
        assert await is_revoked(jti="x", subject="7", issued_at=future_iat) is False


@pytest.mark.asyncio
async def test_is_revoked_treats_missing_iat_as_revoked_when_cutoff_set() -> None:
    with Cache.fake():
        await revoke_all_for_user("7", ttl_seconds=900)
        assert await is_revoked(jti="x", subject="7", issued_at=None) is True


@pytest.mark.asyncio
async def test_no_cutoff_means_not_revoked() -> None:
    with Cache.fake():
        assert await is_revoked(jti="x", subject="nobody", issued_at=None) is False


@pytest.mark.asyncio
async def test_checks_fail_open_without_cache_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    # Facade unbound → checks must not raise, and must report "not revoked".
    monkeypatch.setattr(Cache, "manager", None)
    assert await is_token_denied("abc") is False
    assert await revoked_before_for_user("7") is None
    assert await is_revoked(jti="abc", subject="7", issued_at=123) is False
    # Writes must not raise either.
    await deny_token("abc", expires_at_epoch=int(time.time()) + 900)
    await revoke_all_for_user("7", ttl_seconds=900)
