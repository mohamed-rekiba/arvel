"""Integration (feature flags) — the ``database`` feature-flag driver against a real
PostgreSQL, not SQLite: resolved values persist to the ``features`` table, and a brand-new
``FeatureManager``/``DatabaseFeatureStore`` (no in-process state at all) sees them — the store
survives a fresh process, not just a fresh request."""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver
from arvel.features import DatabaseFeatureStore, FeatureManager, FeatureValue
from arvel.kernel import Application

pytestmark = pytest.mark.integration


def _database_backed_manager(app: Application) -> FeatureManager:
    app.make("config").set("features", {"driver": "database"})
    return FeatureManager(app)


async def test_database_driver_resolves_once_and_persists_across_manager_instances(
    postgres_url: str,
) -> None:
    db = ConnectionResolver({"default": {"url": postgres_url}})
    FeatureValue.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(FeatureValue.__table__))

        manager = _database_backed_manager(Application())
        calls: list[str] = []

        def resolver(scope: Any) -> bool:
            calls.append(scope)
            return scope == "user-a"

        manager.define("beta", resolver)
        assert await manager.active("beta", "user-a") is True
        assert await manager.active("beta", "user-a") is True  # served from Postgres, not re-run
        assert calls == ["user-a"]
        assert await manager.active("beta", "user-b") is False  # a different scope resolves fresh
        assert calls == ["user-a", "user-b"]

        # a brand-new manager + store (no resolvers registered, no in-process cache at all) still
        # sees both stored rows.
        fresh_store = DatabaseFeatureStore()
        assert await fresh_store.get("beta", "user-a") is True
        assert await fresh_store.get("beta", "user-b") is False
    finally:
        await db.execute(sa.schema.DropTable(FeatureValue.__table__))
        await db.dispose()


async def test_database_driver_rich_value_and_purge_on_postgres(postgres_url: str) -> None:
    db = ConnectionResolver({"default": {"url": postgres_url}})
    FeatureValue.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(FeatureValue.__table__))

        store = DatabaseFeatureStore()
        await store.put("variant", "user-a", "purple")
        await store.put("variant", "user-b", "orange")
        assert await store.get("variant", "user-a") == "purple"
        assert await store.get("variant", "user-b") == "orange"

        await store.purge("variant")
        from arvel.features import _MISSING  # pyright: ignore[reportPrivateUsage]

        assert await store.get("variant", "user-a") is _MISSING
        assert await store.get("variant", "user-b") is _MISSING
    finally:
        await db.execute(sa.schema.DropTable(FeatureValue.__table__))
        await db.dispose()


def _load_skeleton_migration(fname: str) -> Any:
    """Execute a shipped skeleton migration template and return its ``Migration`` instance —
    the exact table shape a scaffolded app runs, not one hand-built from ``FeatureValue.__table__``
    (which only ever agrees with itself and so can't catch a model/migration column-type
    mismatch — DR-0061)."""
    from pathlib import Path

    from arvel.database.migrations import Migration

    path = Path("src/arvel/console/_skeleton/app/database/migrations") / fname
    ns: dict[str, Any] = {}
    exec(compile(path.read_text(), str(path), "exec"), ns)  # noqa: S102 - trusted skeleton template
    cls = next(
        v
        for v in ns.values()
        if isinstance(v, type) and issubclass(v, Migration) and v is not Migration
    )
    return cls()


async def test_database_driver_round_trips_through_the_shipped_migration_on_postgres(
    postgres_url: str,
) -> None:
    """DR-0062: a json-cast field (``FeatureValue.value``) always binds as TEXT (the
    ``_build_table`` TEXT_CASTS contract) — the shipped ``create_features_table`` skeleton
    migration's column must agree (``t.text``, not ``t.json``) or asyncpg rejects the write
    (``DatatypeMismatchError``); SQLite's untyped columns hid this (see
    ``tests/test_features_activitylog_migrations.py`` for the SQLite counterpart). A bool AND a
    bare string flag value both round-trip through the wrapped ``{"v": value}`` payload, and a
    toggle is visible to a completely FRESH store/connection (cross-process persistence, not an
    in-memory cache)."""
    from arvel.database.migrations import Migrator

    db = ConnectionResolver({"default": {"url": postgres_url}})
    try:
        await Migrator(db).run(
            [_load_skeleton_migration("0001_01_01_000008_create_features_table.py.tmpl")]
        )
        FeatureValue.set_connection(db)
        store = DatabaseFeatureStore()
        await store.put("promoted-deals", "user:1", True)
        await store.put("theme", "user:2", "midnight")
        assert await store.get("promoted-deals", "user:1") is True
        assert await store.get("theme", "user:2") == "midnight"

        # toggle: write again, then read via a BRAND NEW store/connection — proves the flip is
        # visible cross-process, not served from anything in-memory.
        await store.put("promoted-deals", "user:1", False)
        fresh_db = ConnectionResolver({"default": {"url": postgres_url}})
        FeatureValue.set_connection(fresh_db)
        try:
            assert await DatabaseFeatureStore().get("promoted-deals", "user:1") is False
        finally:
            await fresh_db.dispose()
            FeatureValue.set_connection(db)
    finally:
        FeatureValue.set_connection(None)
        await db.execute(sa.schema.DropTable(FeatureValue.__table__))
        await db.dispose()


async def test_activitylog_properties_round_trips_through_the_shipped_migration_on_postgres(
    postgres_url: str,
) -> None:
    """DR-0062's sibling: ``Activity.properties`` carries the identical json-cast/TEXT_CASTS
    contract as ``FeatureValue.value`` — same latent bug, same fix, never exercised on real
    Postgres before (SQLite hid it here too)."""
    from arvel.activitylog import Activity
    from arvel.database.migrations import Migrator

    db = ConnectionResolver({"default": {"url": postgres_url}})
    try:
        await Migrator(db).run(
            [_load_skeleton_migration("0001_01_01_000009_create_activity_log_table.py.tmpl")]
        )
        Activity.set_connection(db)
        await Activity.create(
            log_name="test",
            description="did a thing",
            properties={"old": {"a": 1}, "attributes": {"a": 2}},
        )
        row = await Activity.where("log_name", "test").first()
        assert row is not None
        assert row.properties == {"old": {"a": 1}, "attributes": {"a": 2}}
    finally:
        Activity.set_connection(None)
        await db.execute(sa.schema.DropTable(Activity.__table__))
        await db.dispose()
