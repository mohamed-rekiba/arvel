"""Auth (G10 hardening) — rehash-on-login: a stale password hash is upgraded on a correct login."""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from pwdlib.hashers.argon2 import Argon2Hasher

from arvel.auth import Authenticatable, AuthManager
from arvel.database import ConnectionResolver, Model
from arvel.security import Hasher


class User(Model, Authenticatable):
    __fields__ = {"email": str, "password": str}
    __fillable__ = ["email"]  # password set directly (guarded)


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    User.set_connection(db)
    await db.execute(sa.schema.CreateTable(User.__table__))
    return db


def _stale_hash(plain: str) -> str:
    """A genuinely outdated argon2 hash (weak params) → recommended Hasher flags it for rehash."""
    return Argon2Hasher(time_cost=1, memory_cost=8, parallelism=1).hash(plain)


async def _provider(credentials: dict[str, Any]) -> Any:
    return await User.where(email=credentials["email"]).first()


@pytest.mark.asyncio
async def test_stale_hash_is_upgraded_on_successful_login() -> None:
    db = await _setup()
    try:
        user = await User.create(email="ada@example.com")
        user.password = _stale_hash("secret")
        await user.save()
        old = user.password
        assert Hasher().needs_rehash("secret", old)  # precondition: the stored hash is stale

        ok = await AuthManager().attempt(
            {"email": "ada@example.com", "password": "secret"}, _provider
        )
        assert ok is True

        fresh = await User.where(email="ada@example.com").first()
        assert fresh.password != old  # upgraded
        assert Hasher().check("secret", fresh.password)  # still the same password
        assert not Hasher().needs_rehash("secret", fresh.password)  # now current
    finally:
        AuthManager().logout()
        await db.dispose()


@pytest.mark.asyncio
async def test_current_hash_is_not_rehashed() -> None:
    db = await _setup()
    try:
        user = await User.create(email="ada@example.com")
        user.password = Hasher().make("secret")  # already current
        await user.save()
        current = user.password

        assert await AuthManager().attempt(
            {"email": "ada@example.com", "password": "secret"}, _provider
        )
        fresh = await User.where(email="ada@example.com").first()
        assert fresh.password == current  # untouched
    finally:
        AuthManager().logout()
        await db.dispose()


@pytest.mark.asyncio
async def test_wrong_password_never_rehashes() -> None:
    db = await _setup()
    try:
        user = await User.create(email="ada@example.com")
        user.password = _stale_hash("secret")
        await user.save()
        old = user.password

        assert (
            await AuthManager().attempt(
                {"email": "ada@example.com", "password": "WRONG"}, _provider
            )
            is False
        )
        fresh = await User.where(email="ada@example.com").first()
        assert fresh.password == old  # failed login → no upgrade
    finally:
        await db.dispose()


@pytest.mark.asyncio
async def test_rehash_skipped_for_non_persistable_user() -> None:
    """A user double without set_auth_password/save must not crash rehash — it's a safe no-op."""

    class Bare(Authenticatable):
        def __init__(self) -> None:
            self.id = 1
            self.password = _stale_hash("secret")

    bare = Bare()
    original = bare.password
    # set_auth_password exists (from Authenticatable) but there's no save() → guarded no-op
    await AuthManager._rehash_if_needed(bare, "secret")
    assert bare.password == original  # unchanged, and no exception raised
