"""Auth (G8 hardening) — sign out of all devices (persistent-credential revocation)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from arvel.auth.devices import logout_everywhere
from arvel.auth.refresh import RefreshToken, issue_refresh_token, rotate_refresh_token
from arvel.auth.remember import RememberToken, issue_remember_token, recall_remember_token
from arvel.auth.tokens import ApiToken, create_token, resolve_token, revoke_all_tokens
from arvel.database import ConnectionResolver


class FakeUser:
    def __init__(self, uid: int) -> None:
        self.id = uid

    def get_auth_identifier(self) -> int:
        return self.id


async def _db() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (RefreshToken, RememberToken, ApiToken):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return db


async def test_logout_everywhere_revokes_all_persistent_credentials() -> None:
    db = await _db()
    try:
        refresh42 = await issue_refresh_token(42)
        remember42 = await issue_remember_token(42)
        api42, _ = await create_token(FakeUser(42))
        # a bystander whose credentials must survive
        remember99 = await issue_remember_token(99)
        api99, _ = await create_token(FakeUser(99))
        refresh99 = await issue_refresh_token(99)

        await logout_everywhere(FakeUser(42))

        # user 42: every persistent credential is dead
        assert await rotate_refresh_token(refresh42) is None  # refresh revoked
        assert await recall_remember_token(remember42) is None  # remember deleted
        assert await resolve_token(api42) is None  # API token deleted

        # user 99: untouched
        assert await recall_remember_token(remember99) is not None
        assert await resolve_token(api99) is not None
        assert await rotate_refresh_token(refresh99) is not None
    finally:
        await db.dispose()


async def test_revoke_all_tokens_is_scoped_to_one_user() -> None:
    db = await _db()
    try:
        a, _ = await create_token(FakeUser(1))
        b, _ = await create_token(FakeUser(2))
        await revoke_all_tokens(1)
        assert await resolve_token(a) is None  # revoked
        assert await resolve_token(b) is not None  # other user's token survives
    finally:
        await db.dispose()


async def test_logout_everywhere_works_with_a_plain_id_user() -> None:
    """The get_auth_identifier-less fallback (bare .id) still revokes."""
    db = await _db()
    try:
        api = (await create_token(SimpleNamespace(id=7)))[0]
        await logout_everywhere(SimpleNamespace(id=7))
        assert await resolve_token(api) is None
    finally:
        await db.dispose()


async def test_logout_everywhere_is_best_effort_and_loud_on_partial_failure() -> None:
    """If one store fails, the others still run and the failure is raised (not swallowed)."""
    db = await _db()
    try:
        api = (await create_token(FakeUser(3)))[0]
        # Break the remember-token store mid-sequence; API tokens (revoked first) must still die.
        original = RememberToken.query
        RememberToken.query = staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("boom")))  # type: ignore[method-assign]
        try:
            with pytest.raises(ExceptionGroup):
                await logout_everywhere(FakeUser(3))
        finally:
            RememberToken.query = original  # type: ignore[method-assign]
        assert await resolve_token(api) is None  # API tokens revoked despite the remember failure
    finally:
        await db.dispose()


async def test_unidentified_user_is_rejected() -> None:
    with pytest.raises(ValueError, match="unidentified"):
        await logout_everywhere(SimpleNamespace())
