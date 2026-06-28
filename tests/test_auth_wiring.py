"""Phase 4 — app wiring: DB-backed IdentityStore round-trip + AuthServiceProvider registration."""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa

from arvel.auth.guards import GuardManager
from arvel.auth.identity import AuthIdentity, DbIdentityStore, Principal, UserProvider
from arvel.auth.provider import AuthServiceProvider
from arvel.database import ConnectionResolver, Model


class User(Model):
    __fields__ = {"email": str}
    __fillable__ = ["email"]


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (User, AuthIdentity):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return db


# --- DB-backed IdentityStore --------------------------------------------------


@pytest.mark.asyncio
async def test_db_identity_store_roundtrip() -> None:
    db = await _setup()
    try:
        user = await User.create(email="ada@corp.com")
        store = DbIdentityStore(User)
        await store.link(Principal(provider="keycloak", subject="kc-1"), user)

        ident = await store.find("keycloak", "kc-1")
        assert ident is not None
        resolved_user = await store.user_for(ident)
        assert resolved_user.id == user.id
        by_email = await store.user_by_email("ada@corp.com")
        assert by_email.id == user.id
        assert await store.count_for_user(user) == 1

        await store.unlink(user, "keycloak", "kc-1")
        assert await store.find("keycloak", "kc-1") is None
        assert await store.count_for_user(user) == 0
    finally:
        await db.dispose()


@pytest.mark.asyncio
async def test_user_provider_resolves_through_db_store() -> None:
    db = await _setup()
    try:
        user = await User.create(email="ada@corp.com")
        store = DbIdentityStore(User)
        await store.link(Principal(provider="keycloak", subject="kc-1"), user)

        provider = UserProvider(store)
        resolved = await provider.resolve(Principal(provider="keycloak", subject="kc-1"))
        assert resolved is not None
        assert resolved.id == user.id
    finally:
        await db.dispose()


# --- AuthServiceProvider registration -----------------------------------------


class _FakeApp:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.bindings: dict[str, Any] = {}
        self._config = config or {}

    def singleton(self, name: str, factory: Any) -> None:
        self.bindings[name] = factory

    def config(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)


def test_provider_registers_guard_manager() -> None:
    app = _FakeApp()
    AuthServiceProvider(app).register()  # type: ignore[arg-type]
    assert "guard" in app.bindings
    assert isinstance(app.bindings["guard"](app), GuardManager)


def test_user_provider_binding_needs_user_model() -> None:
    app = _FakeApp()
    AuthServiceProvider(app).register()  # type: ignore[arg-type]
    assert "auth.user_provider" in app.bindings
    # unconfigured → None; the app must set auth.user_model
    assert app.bindings["auth.user_provider"](app) is None


def test_user_provider_binding_built_when_configured() -> None:
    app = _FakeApp({"auth.user_model": User, "auth.trusted_email_providers": ["keycloak"]})
    AuthServiceProvider(app).register()  # type: ignore[arg-type]
    provider = app.bindings["auth.user_provider"](app)
    assert isinstance(provider, UserProvider)
