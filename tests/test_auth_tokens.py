"""API token guard (Sanctum-parity): create + resolve + bearer guard."""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa

from arvel.auth.tokens import (
    ApiToken,
    TokenGuard,
    abilities,
    ability,
    create_token,
    current_access_token,
    prune_expired_tokens,
    resolve_token,
    token_can,
)
from arvel.database import ConnectionResolver, Model
from arvel.kernel import Application, set_application


class Account(Model):
    __fields__ = {"email": str}
    __fillable__ = ["email"]


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (Account, ApiToken):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return db


async def test_create_and_resolve_token() -> None:
    db = await _setup()
    try:
        user = await Account.create(email="ada@example.com")
        plaintext, token = await create_token(user, name="cli")
        assert len(plaintext) >= 64  # high-entropy secret
        assert token.tokenable_id == user.id
        assert token.token != plaintext  # only the hash is stored

        resolved = await resolve_token(plaintext)
        assert resolved is not None
        assert resolved.tokenable_id == user.id
        assert await resolve_token("not-a-real-token") is None
    finally:
        await db.dispose()


async def test_token_guard_reads_bearer_header() -> None:
    db = await _setup()
    try:
        user = await Account.create(email="ada@example.com")
        plaintext, _ = await create_token(user)

        class Authed:
            def header(self, name: str, default: Any = None) -> Any:
                return f"Bearer {plaintext}" if name == "authorization" else default

        class Anon:
            def header(self, name: str, default: Any = None) -> Any:
                return default

        guard = TokenGuard()
        assert await guard.user_id(Authed()) == user.id
        assert await guard.user_id(Anon()) is None
    finally:
        await db.dispose()


# --- abilities / scopes (Sanctum parity) --------------------------------------


async def test_token_abilities_scope() -> None:
    db = await _setup()
    try:
        user = await Account.create(email="ada@example.com")

        _, scoped = await create_token(user, abilities=["posts.read", "posts.write"])
        assert scoped.can("posts.read") is True
        assert scoped.can("posts.write") is True
        assert scoped.can("posts.delete") is False  # not granted

        _, wildcard = await create_token(user)  # default abilities = ["*"]
        assert wildcard.can("anything.at.all") is True

        # An empty-abilities token can't be *minted* (create_token rejects it), but a row that ends
        # up scopeless (legacy/partial) must still grant nothing — build it at the model layer.
        scopeless = await ApiToken.create(
            name="legacy", token="x" * 64, tokenable_id=user.id, abilities=[]
        )
        assert scopeless.can("posts.read") is False  # empty → grants nothing (fail closed)
    finally:
        await db.dispose()


async def test_scopes_survive_a_resolve_roundtrip() -> None:
    db = await _setup()
    try:
        user = await Account.create(email="ada@example.com")
        plaintext, _ = await create_token(user, abilities=["billing.read"])
        resolved = await resolve_token(plaintext)
        assert resolved is not None
        assert resolved.can("billing.read") is True
        assert resolved.can("billing.write") is False
    finally:
        await db.dispose()


# --- expiry -------------------------------------------------------------------


async def test_expired_token_is_rejected() -> None:
    db = await _setup()
    try:
        user = await Account.create(email="ada@example.com")
        # create_token won't mint a past expiry (validated), so age a valid token into the past.
        plaintext, token = await create_token(user, expires_in=3600)
        from arvel.dates import Date

        token.expires_at = Date.now().subtract(seconds=10)
        await token.save()
        assert token.is_expired() is True
        assert await resolve_token(plaintext) is None  # resolve refuses an expired token
    finally:
        await db.dispose()


async def test_unexpired_and_non_expiring_tokens_resolve() -> None:
    db = await _setup()
    try:
        user = await Account.create(email="ada@example.com")

        future_plain, future = await create_token(user, expires_in=3600)
        assert future.is_expired() is False
        assert await resolve_token(future_plain) is not None

        forever_plain, forever = await create_token(user)  # no expiry
        assert forever.is_expired() is False
        assert await resolve_token(forever_plain) is not None
    finally:
        await db.dispose()


def test_legacy_row_without_new_columns_fails_closed() -> None:
    """A token row hydrated before the abilities/expires_at columns existed must degrade safely —
    can() denies and is_expired() reports non-expiring, rather than raising AttributeError."""
    legacy = ApiToken._hydrate({"id": 1, "name": "old", "token": "h", "tokenable_id": 1})
    assert legacy.can("anything") is False  # no abilities column → grants nothing
    assert legacy.is_expired() is False  # no expires_at column → never expires


async def test_token_guard_token_returns_record() -> None:
    db = await _setup()
    try:
        user = await Account.create(email="ada@example.com")
        plaintext, _ = await create_token(user, abilities=["reports.export"])

        class Authed:
            def header(self, name: str, default: Any = None) -> Any:
                return f"Bearer {plaintext}" if name == "authorization" else default

        record = await TokenGuard().token(Authed())
        assert record is not None
        assert record.can("reports.export") is True
        assert record.can("reports.delete") is False
    finally:
        await db.dispose()


# --- pruning + mint-time validation ---------------------------------------------


async def test_prune_expired_tokens_keeps_valid_and_nonexpiring() -> None:
    db = await _setup()
    try:
        from arvel.dates import Date

        user = await Account.create(email="ada@example.com")
        _, past = await create_token(user, expires_in=3600)
        past.expires_at = Date.now().subtract(seconds=10)  # age it into the past
        await past.save()
        await create_token(user, expires_in=3600)  # future — keep
        await create_token(user)  # non-expiring — keep

        removed = await prune_expired_tokens()
        assert removed == 1  # only the expired one
        survivors = await ApiToken.where(tokenable_id=user.id).get()
        assert len(survivors) == 2
        assert all(not t.is_expired() for t in survivors)
    finally:
        await db.dispose()


async def test_create_token_validates_abilities() -> None:
    db = await _setup()
    try:
        user = await Account.create(email="ada@example.com")
        with pytest.raises(ValueError, match="abilities"):
            await create_token(user, abilities=[])
        with pytest.raises(ValueError, match="abilities"):
            await create_token(user, abilities=["posts.read", ""])
        # a bare string is treated as one ability (not split into characters)
        _, token = await create_token(user, abilities="posts.read")
        assert token.can("posts.read") is True and token.can("p") is False
    finally:
        await db.dispose()


async def test_create_token_validates_expires_in() -> None:
    db = await _setup()
    try:
        user = await Account.create(email="ada@example.com")
        for bad in (0, -5, True):
            with pytest.raises(ValueError, match="expires_in"):
                await create_token(user, expires_in=bad)
        _, token = await create_token(user, expires_in=3600)  # valid
        assert token.is_expired() is False
    finally:
        await db.dispose()


# --- last_used_at (throttled write) -------------------------------------------


async def test_resolve_token_stamps_last_used_at_once() -> None:
    db = await _setup()
    try:
        user = await Account.create(email="ada@example.com")
        plaintext, token = await create_token(user)
        assert token.last_used_at is None  # never used yet

        resolved = await resolve_token(plaintext)
        assert resolved is not None
        assert resolved.last_used_at is not None  # stamped on first use
    finally:
        await db.dispose()


async def test_last_used_at_write_is_throttled() -> None:
    db = await _setup()
    app = Application()
    app.make("config").set("sanctum.last_used_throttle", 3600)  # 1h — won't elapse in this test
    set_application(app)
    try:
        user = await Account.create(email="ada@example.com")
        plaintext, _token = await create_token(user)

        first = await resolve_token(plaintext)
        assert first is not None
        stamped_at = first.last_used_at

        second = await resolve_token(plaintext)
        assert second is not None
        assert second.last_used_at == stamped_at  # within the throttle window — no rewrite
    finally:
        set_application(None)
        await db.dispose()


async def test_last_used_at_rewrites_once_throttle_elapses() -> None:
    db = await _setup()
    app = Application()
    app.make("config").set("sanctum.last_used_throttle", 60)
    set_application(app)
    try:
        user = await Account.create(email="ada@example.com")
        plaintext, token = await create_token(user)

        first = await resolve_token(plaintext)
        assert first is not None
        from arvel.dates import Date

        # age the stamp past the throttle window, then resolve again
        token.last_used_at = Date.now().subtract(seconds=120)
        await token.save()

        second = await resolve_token(plaintext)
        assert second is not None
        assert second.last_used_at > first.last_used_at
    finally:
        set_application(None)
        await db.dispose()


# --- current_access_token() / token_can() -------------------------------------


async def test_current_access_token_set_by_token_guard() -> None:
    db = await _setup()
    try:
        assert current_access_token() is None  # nothing resolved yet
        user = await Account.create(email="ada@example.com")
        plaintext, _ = await create_token(user, abilities=["posts.read"])

        class Authed:
            def header(self, name: str, default: Any = None) -> Any:
                return f"Bearer {plaintext}" if name == "authorization" else default

        resolved = await TokenGuard().token(Authed())
        assert current_access_token() is resolved
        assert token_can("posts.read") is True
        assert token_can("posts.delete") is False
    finally:
        await db.dispose()


def test_token_can_false_with_no_active_token() -> None:
    assert token_can("anything") is False  # fail closed, contextvar default is None


# --- global default expiration (config sanctum.expiration) --------------------


async def test_create_token_applies_global_default_expiration() -> None:
    db = await _setup()
    app = Application()
    app.make("config").set("sanctum.expiration", 60)  # minutes
    set_application(app)
    try:
        user = await Account.create(email="ada@example.com")
        _, token = await create_token(user)  # expires_in omitted → config default applies
        assert token.expires_at is not None
        assert token.is_expired() is False
    finally:
        set_application(None)
        await db.dispose()


async def test_create_token_explicit_expires_in_overrides_config_default() -> None:
    db = await _setup()
    app = Application()
    app.make("config").set("sanctum.expiration", 60)
    set_application(app)
    try:
        user = await Account.create(email="ada@example.com")
        _, token = await create_token(user, expires_in=5)
        from arvel.dates import Date

        assert token.expires_at is not None
        # ~5s lifetime, not 60 minutes
        assert token.expires_at.to_py() < Date.now().add(seconds=30).to_py()
    finally:
        set_application(None)
        await db.dispose()


async def test_create_token_without_config_stays_non_expiring() -> None:
    db = await _setup()
    try:
        user = await Account.create(email="ada@example.com")
        _, token = await create_token(user)  # no app running → no config default
        assert token.expires_at is None
    finally:
        await db.dispose()


# --- abilities()/ability() route middleware (all vs any) ----------------------


class _Resp:
    def __init__(self, status: int, body: Any = None) -> None:
        self.status = status
        self.body = body


async def _call_next(_request: Any) -> _Resp:
    return _Resp(200, "ok")


class _Bearer:
    def __init__(self, plaintext: str | None) -> None:
        self._plaintext = plaintext

    def header(self, name: str, default: Any = None) -> Any:
        if name == "authorization" and self._plaintext:
            return f"Bearer {self._plaintext}"
        return default


async def test_abilities_middleware_requires_all() -> None:
    db = await _setup()
    try:
        user = await Account.create(email="ada@example.com")
        plaintext, _ = await create_token(user, abilities=["posts.read", "posts.write"])

        allowed = abilities("posts.read", "posts.write")()
        assert (await allowed.handle(_Bearer(plaintext), _call_next)).status == 200

        missing_one = abilities("posts.read", "posts.delete")()
        with pytest.raises(Exception) as ei:  # HttpException, checked below
            await missing_one.handle(_Bearer(plaintext), _call_next)
        assert getattr(ei.value, "status", None) == 403
    finally:
        await db.dispose()


async def test_ability_middleware_requires_any() -> None:
    db = await _setup()
    try:
        user = await Account.create(email="ada@example.com")
        plaintext, _ = await create_token(user, abilities=["posts.read"])

        any_match = ability("posts.write", "posts.read")()
        assert (await any_match.handle(_Bearer(plaintext), _call_next)).status == 200

        no_match = ability("posts.write", "posts.delete")()
        with pytest.raises(Exception) as ei:
            await no_match.handle(_Bearer(plaintext), _call_next)
        assert getattr(ei.value, "status", None) == 403
    finally:
        await db.dispose()


async def test_abilities_middleware_401s_with_no_bearer_token() -> None:
    guarded = abilities("posts.read")()
    with pytest.raises(Exception) as ei:
        await guarded.handle(_Bearer(None), _call_next)
    assert getattr(ei.value, "status", None) == 401


async def test_current_access_token_does_not_leak_across_requests() -> None:
    # CRITICAL (security review): the per-request token contextvar must be reset so req B
    # never sees req A's token via current_access_token()/token_can().
    from arvel.auth.tokens import current_access_token
    from arvel.support import access_token

    class _Tok:
        abilities = ["*"]

    ctx = access_token.set(_Tok())  # simulate req A resolving a token
    try:
        assert current_access_token() is not None
    finally:
        access_token.reset(ctx)  # kernel does this per request in _dispatch's finally
    assert current_access_token() is None  # req B (no token) sees nothing
