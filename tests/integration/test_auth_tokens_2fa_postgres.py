"""15 AUTH-AUTHZ — API tokens (last_used_at) + 2FA, against a real
PostgreSQL (not just SQLite — the encrypted/hashed casts + real DateTime column round-trip need a
real dialect, not just the ORM's in-memory model logic)."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
import sqlalchemy as sa

from arvel.auth.tokens import ApiToken, create_token, resolve_token
from arvel.auth.two_factor import (
    TwoFactor,
    confirm_two_factor,
    enable_two_factor,
    regenerate_recovery_codes,
    verify_two_factor,
)
from arvel.database import Builder, ConnectionResolver, Model
from arvel.kernel import Application, set_application
from arvel.security import Encrypter

pytestmark = pytest.mark.integration


class Account(Model):
    __fields__: ClassVar[dict[str, Any]] = {"email": str}
    __fillable__: ClassVar[list[str]] = ["email"]


class TwoFactorUser(Model):
    """A user model that opts into encrypted-at-rest 2FA columns, per docs/auth/two-factor.md."""

    __table_name__ = "two_factor_users"
    __fields__: ClassVar[dict[str, Any]] = {
        "email": str,
        "two_factor_secret": sa.Text(),
        "two_factor_recovery_codes": sa.Text(),
        "two_factor_confirmed_at": str,
    }
    __fillable__: ClassVar[list[str]] = ["email"]
    __casts__: ClassVar[dict[str, str]] = {
        "two_factor_secret": "encrypted",
        "two_factor_recovery_codes": "encrypted:array",
        "two_factor_confirmed_at": "datetime",
    }


async def test_token_last_used_at_persists_on_postgres(postgres_url: str) -> None:
    app = Application()
    set_application(app)
    db = ConnectionResolver({"default": {"url": postgres_url}})
    Account.set_connection(db)
    ApiToken.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(Account.__table__))
        await db.execute(sa.schema.CreateTable(ApiToken.__table__))

        user = await Account.create(email="ada@example.com")
        plaintext, token = await create_token(user, name="ci")
        assert token.last_used_at is None

        resolved = await resolve_token(plaintext)
        assert resolved is not None
        assert resolved.last_used_at is not None  # stamped + persisted

        reloaded = await ApiToken.where(id=token.id).first()
        assert reloaded is not None
        assert reloaded.last_used_at is not None  # survives the round-trip, not just in-memory
    finally:
        set_application(None)
        await db.dispose()


async def test_two_factor_lifecycle_persists_encrypted_on_postgres(postgres_url: str) -> None:
    app = Application()
    app.instance("encrypter", Encrypter(Encrypter.generate_key()))
    set_application(app)
    db = ConnectionResolver({"default": {"url": postgres_url}})
    TwoFactorUser.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(TwoFactorUser.__table__))

        user = await TwoFactorUser.create(email="ada@example.com")
        enrollment = await enable_two_factor(user)
        assert user.two_factor_confirmed_at is None

        # the raw column holds ciphertext, not the plaintext secret or recovery codes — a raw
        # (non-hydrating) builder query bypasses the "encrypted" cast that would decrypt it back
        raw_rows = await (
            Builder(TwoFactorUser.__table__, db)
            .select_raw("two_factor_secret")
            .where("id", user.id)
            .get()
        )
        raw_secret = raw_rows[0]["two_factor_secret"]
        assert raw_secret is not None
        assert user.two_factor_secret not in raw_secret  # ciphertext, not plaintext, on disk

        code = TwoFactor.current_code(user.two_factor_secret)
        assert await confirm_two_factor(user, code) is True
        assert user.two_factor_confirmed_at is not None

        reloaded = await TwoFactorUser.where(id=user.id).first()
        assert reloaded is not None
        assert reloaded.two_factor_confirmed_at is not None  # persisted, not just in-memory
        assert reloaded.two_factor_secret == user.two_factor_secret  # decrypts back correctly

        recovery_code = enrollment.recovery_codes[0]
        assert await verify_two_factor(reloaded, recovery_code) is True  # consumes it
        assert await verify_two_factor(reloaded, recovery_code) is False  # single-use

        new_codes = await regenerate_recovery_codes(reloaded)
        refetched = await TwoFactorUser.where(id=user.id).first()
        assert refetched is not None
        assert await verify_two_factor(refetched, new_codes[0]) is True
    finally:
        set_application(None)
        await db.dispose()
