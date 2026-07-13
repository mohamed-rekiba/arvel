"""Shipped migrations create working features/activity_log tables; feature purge-all + values (H11)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from arvel.database import ConnectionResolver
from arvel.database.migrations import Migration, Migrator
from arvel.features import DatabaseFeatureStore, FeatureManager, FeatureValue

_MIGRATIONS = Path("src/arvel/console/_skeleton/app/database/migrations")


def _load(fname: str) -> Migration:
    ns: dict[str, Any] = {}
    path = _MIGRATIONS / fname
    exec(compile(path.read_text(), str(path), "exec"), ns)  # noqa: S102 - trusted skeleton template
    cls = next(
        v
        for v in ns.values()
        if isinstance(v, type) and issubclass(v, Migration) and v is not Migration
    )
    return cls()


async def test_shipped_migrations_create_working_tables() -> None:
    db = ConnectionResolver()
    try:
        ran = await Migrator(db).run(
            [
                _load("0001_01_01_000008_create_features_table.py.tmpl"),
                _load("0001_01_01_000009_create_activity_log_table.py.tmpl"),
            ]
        )
        assert ran == 2
        # the database feature driver persists against the shipped features table
        FeatureValue.set_connection(db)
        store = DatabaseFeatureStore()
        await store.put("beta", "user:1", True)
        assert await store.get("beta", "user:1") is True
        # composite unique (name, scope): a second raw insert for the same pair is rejected
        import sqlalchemy as sa
        from sqlalchemy.exc import IntegrityError

        features = sa.table("features", sa.column("name"), sa.column("scope"), sa.column("value"))
        with pytest.raises(IntegrityError):
            async with db.engine().begin() as conn:
                await conn.execute(features.insert().values(name="beta", scope="user:1", value="x"))
    finally:
        await db.dispose()


async def test_purge_all_and_values() -> None:
    fm = FeatureManager()
    fm.define("beta", lambda _s: True)
    fm.define("gamma", lambda _s: "on")

    assert await fm.values() == {"beta": True, "gamma": "on"}
    assert await fm.values(["beta"]) == {"beta": True}

    await fm.purge()  # no arg → clears every defined flag
    # after purge the store is empty; a fresh resolve re-runs the resolver (no stored value)
    assert await fm.value("beta") is True
