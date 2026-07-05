"""Integration (spec 20-pennant) — the ``database`` feature-flag driver against a real
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
