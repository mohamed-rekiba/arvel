"""arvel.features — define/resolve/mutate feature flags: per-scope
resolution, resolver memoization (runs once per scope, then the store is served), rich values,
activate/deactivate/forget/purge, class-based features, and the array + sqlite-backed database
drivers. See docs/features.md + spec 20-pennant."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from typer.testing import CliRunner

from arvel.console import build_cli
from arvel.database import ConnectionResolver
from arvel.features import (
    _MISSING,  # pyright: ignore[reportPrivateUsage]
    ArrayFeatureStore,
    DatabaseFeatureStore,
    Feature,
    FeatureManager,
    FeatureValue,
)
from arvel.kernel import Application, set_application

runner = CliRunner()


# --- array driver (the default) ----------------------------------------------
async def test_define_active_inactive_bool_resolver() -> None:
    manager = FeatureManager()
    manager.define("new-ui", lambda scope: scope == "on")
    assert await manager.active("new-ui", "on") is True
    assert await manager.inactive("new-ui", "on") is False
    assert await manager.active("new-ui", "off") is False
    assert await manager.inactive("new-ui", "off") is True


async def test_per_scope_resolution_is_independent() -> None:
    manager = FeatureManager()
    manager.define("beta", lambda scope: scope == "user-a")
    assert await manager.active("beta", "user-a") is True
    assert await manager.active("beta", "user-b") is False


async def test_value_returns_a_rich_value() -> None:
    manager = FeatureManager()
    manager.define("variant", lambda scope: "purple")
    assert await manager.value("variant", "u1") == "purple"
    assert await manager.active("variant", "u1") is True  # truthiness of a non-bool value


async def test_resolver_runs_once_per_scope_then_is_memoized() -> None:
    manager = FeatureManager()
    calls: list[str] = []

    def resolver(scope: Any) -> bool:
        calls.append(scope)
        return True

    manager.define("once", resolver)
    assert await manager.active("once", "u1") is True
    assert await manager.active("once", "u1") is True  # second call: served from the store
    assert calls == ["u1"]  # the resolver ran exactly once
    assert await manager.active("once", "u2") is True  # a different scope: resolver runs again
    assert calls == ["u1", "u2"]


async def test_active_without_a_scope_uses_the_default_global_scope_key() -> None:
    manager = FeatureManager()
    calls: list[Any] = []

    def resolver(scope: Any) -> bool:
        calls.append(scope)
        return True

    manager.define("maintenance", resolver)
    assert await manager.active("maintenance") is True
    assert await manager.active("maintenance") is True
    assert calls == [None]  # resolver ran exactly once for the global scope


async def test_activate_deactivate_override_the_resolver() -> None:
    manager = FeatureManager()
    manager.define("flag", lambda scope: False)
    await manager.activate("flag", "u1")
    assert await manager.active("flag", "u1") is True
    await manager.deactivate("flag", "u1")
    assert await manager.active("flag", "u1") is False


async def test_activate_with_a_rich_value() -> None:
    manager = FeatureManager()
    manager.define("variant", lambda scope: "purple")
    await manager.activate("variant", "u1", value="orange")
    assert await manager.value("variant", "u1") == "orange"


async def test_forget_forces_reresolution() -> None:
    manager = FeatureManager()
    calls = {"n": 0}

    def resolver(_scope: Any) -> int:
        calls["n"] += 1
        return calls["n"]

    manager.define("counter", resolver)
    assert await manager.value("counter", "u1") == 1
    assert await manager.value("counter", "u1") == 1  # memoized
    await manager.forget("counter", "u1")
    assert await manager.value("counter", "u1") == 2  # resolver ran again


async def test_purge_clears_every_scope_for_a_flag() -> None:
    manager = FeatureManager()
    calls = {"n": 0}

    def resolver(_scope: Any) -> int:
        calls["n"] += 1
        return calls["n"]

    manager.define("counter", resolver)
    await manager.value("counter", "u1")
    await manager.value("counter", "u2")
    assert calls["n"] == 2
    await manager.purge("counter")
    await manager.value("counter", "u1")
    await manager.value("counter", "u2")
    assert calls["n"] == 4  # both scopes re-resolved


async def test_class_based_feature_resolves_like_a_closure() -> None:
    class NewUi:
        def resolve(self, scope: Any) -> bool:
            return scope == "beta-tester"

    manager = FeatureManager()
    manager.define("new-ui", NewUi)  # a bare class — instantiated once, dispatched via .resolve
    assert await manager.active("new-ui", "beta-tester") is True
    assert await manager.active("new-ui", "someone-else") is False


async def test_when_branches_on_the_resolved_value() -> None:
    manager = FeatureManager()
    manager.define("variant", lambda scope: "purple" if scope == "u1" else False)
    assert await manager.when("variant", "u1", lambda v: f"active:{v}", "inactive") == (
        "active:purple"
    )
    assert await manager.when("variant", "u2", "active", lambda v: "inactive") == "inactive"


async def test_for_scope_is_the_same_read_mutate_surface() -> None:
    manager = FeatureManager()
    manager.define("beta", lambda scope: scope == "u1")
    scoped_a = manager.for_("u1")
    scoped_b = manager.for_("u2")
    assert await scoped_a.active("beta") is True
    assert await scoped_b.active("beta") is False
    await scoped_b.activate("beta")
    assert await scoped_b.active("beta") is True


async def test_no_such_feature_raises_lookup_error() -> None:
    manager = FeatureManager()
    try:
        await manager.active("nope")
    except LookupError as exc:
        assert "nope" in str(exc)
    else:
        raise AssertionError("expected LookupError")


async def test_array_store_purge_only_touches_the_named_flag() -> None:
    store = ArrayFeatureStore()
    await store.put("a", "u1", True)
    await store.put("b", "u1", True)
    await store.purge("a")
    assert await store.get("a", "u1") is _MISSING
    assert await store.get("b", "u1") is True


# --- Feature front door (app-bound) ------------------------------------------
async def test_feature_front_door_resolves_the_app_bound_manager() -> None:
    app = Application()
    app.instance("features", FeatureManager(app))
    set_application(app)
    try:
        Feature.define("beta", lambda scope: scope == "u1")
        assert await Feature.for_("u1").active("beta") is True
        assert await Feature.for_("u2").active("beta") is False
        assert Feature.defined() == ["beta"]
    finally:
        set_application(None)


async def test_feature_without_a_booted_app_raises() -> None:
    set_application(None)
    try:
        await Feature.active("beta")
    except RuntimeError as exc:
        assert "booted application" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


# --- database driver (sqlite) -------------------------------------------------
async def _sqlite_db() -> ConnectionResolver:
    db = ConnectionResolver()
    FeatureValue.set_connection(db)
    await db.execute(sa.schema.CreateTable(FeatureValue.__table__))
    return db


def _database_backed_manager() -> FeatureManager:
    app = Application()
    app.make("config").set("features", {"driver": "database"})
    return FeatureManager(app)


async def test_database_driver_resolves_once_per_scope_and_persists() -> None:
    db = await _sqlite_db()
    try:
        manager = _database_backed_manager()
        calls: list[str] = []

        def resolver(scope: Any) -> bool:
            calls.append(scope)
            return scope == "u1"

        manager.define("beta", resolver)
        assert await manager.active("beta", "u1") is True
        assert await manager.active("beta", "u1") is True  # served from the sqlite row
        assert calls == ["u1"]  # the resolver ran exactly once

        assert await manager.active("beta", "u2") is False
        assert calls == ["u1", "u2"]

        # a brand-new manager (no resolvers, no in-process state) still sees the stored rows —
        # the database driver, unlike array, persists across a fresh instance/process.
        fresh_manager = _database_backed_manager()
        assert await fresh_manager.driver().get("beta", "u1") is True
        assert await fresh_manager.driver().get("beta", "u2") is False
    finally:
        await db.dispose()


async def test_database_feature_store_put_forget_purge() -> None:
    db = await _sqlite_db()
    try:
        store = DatabaseFeatureStore()
        await store.put("flag", "u1", True)
        await store.put("flag", "u2", "variant")
        assert await store.get("flag", "u1") is True
        assert await store.get("flag", "u2") == "variant"

        await store.forget("flag", "u1")
        assert await store.get("flag", "u1") is _MISSING
        assert await store.get("flag", "u2") == "variant"  # untouched

        await store.purge("flag")
        assert await store.get("flag", "u2") is _MISSING
    finally:
        await db.dispose()


# --- CLI: feature:list / feature:purge ---------------------------------------
def test_feature_list_prints_defined_flags() -> None:
    app = Application()
    manager = FeatureManager(app)
    manager.define("beta", lambda scope: True)
    manager.define("alpha", lambda scope: False)
    app.instance("features", manager)
    set_application(app)
    try:
        result = runner.invoke(build_cli(), ["feature:list"])
        assert result.exit_code == 0, result.output
        assert "alpha" in result.output
        assert "beta" in result.output
    finally:
        set_application(None)


def test_feature_list_with_no_features_defined() -> None:
    app = Application()
    app.instance("features", FeatureManager(app))
    set_application(app)
    try:
        result = runner.invoke(build_cli(), ["feature:list"])
        assert result.exit_code == 0, result.output
        assert "no features defined" in result.output
    finally:
        set_application(None)


def test_feature_purge_clears_stored_values() -> None:
    import asyncio

    app = Application()
    manager = FeatureManager(app)
    manager.define("flag", lambda scope: True)
    app.instance("features", manager)
    set_application(app)
    try:
        asyncio.run(manager.activate("flag", "u1"))
        result = runner.invoke(build_cli(), ["feature:purge", "flag"])
        assert result.exit_code == 0, result.output
        assert "purged 'flag'" in result.output
        assert asyncio.run(manager.driver().get("flag", "u1")) is _MISSING
    finally:
        set_application(None)


async def test_a_cached_falsy_value_is_not_re_resolved() -> None:
    # review nit: the _MISSING sentinel must distinguish "unstored" from a stored falsy value —
    # a resolver returning False must run exactly ONCE, not re-run because the value is falsy
    manager = FeatureManager()
    calls: list[str] = []

    def resolver(scope: Any) -> bool:
        calls.append(scope)
        return False  # a legitimately falsy flag value

    manager.define("off", resolver)
    assert await manager.active("off", "u1") is False
    assert await manager.active("off", "u1") is False  # served from the store, not re-resolved
    assert await manager.value("off", "u1") is False
    assert calls == ["u1"]  # resolver ran exactly once despite the falsy cached value
