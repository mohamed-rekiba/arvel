"""Postgres-only DDL features (materialized views, CREATE EXTENSION, GIN/GiST) don't silently fail
on another dialect — they emit a `postgres_only_feature` warning and degrade: MV → plain view,
extension → skip, GIN/GiST → plain index. So a sqlite run is honest and still works."""

from __future__ import annotations

import sqlalchemy as sa

import arvel.database.migrations as mig
from arvel.database import ConnectionResolver
from arvel.database.migrations import Migration, Migrator, Schema


class _PgFeatures(Migration):
    def up(self, schema: Schema) -> None:
        schema.create("nums", lambda t: (t.id(), t.integer("n")))
        schema.create_extension("uuid-ossp")  # Postgres-only → skipped on sqlite
        schema.create_materialized_view(  # → a plain view on sqlite
            "v_nums", sa.select(sa.text("n")).select_from(sa.text("nums"))
        )

    def down(self, schema: Schema) -> None:
        schema.drop("nums")


async def test_pg_only_features_degrade_and_warn_on_sqlite(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        mig,
        "_warn_pg_only",
        lambda feature, dialect, *, action: calls.append((feature, action)),
    )
    db = ConnectionResolver()
    try:
        await Migrator(db).run([_PgFeatures()])
        await db.execute(sa.text("INSERT INTO nums (n) VALUES (7)"))
        value = await db.scalar(sa.text("SELECT n FROM v_nums"))
    finally:
        await db.dispose()

    assert value == 7  # the materialized view degraded to a live, queryable plain view
    actions = {action for _feature, action in calls}
    assert "plain view" in actions  # MV → view
    assert "skipped" in actions  # extension skipped


def test_gin_index_warns_on_non_postgres(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        mig,
        "_warn_pg_only",
        lambda feature, dialect, *, action: calls.append((feature, action)),
    )

    class _Op:
        def create_table(self, *a, **k) -> None:  # type: ignore[no-untyped-def]
            ...

        def create_index(self, *a, **k) -> None:  # type: ignore[no-untyped-def]
            ...

        def get_bind(self) -> object:
            return type("B", (), {"dialect": type("D", (), {"name": "sqlite"})()})()

    Schema(_Op()).create("docs", lambda t: (t.id(), t.jsonb("data"), t.gin_index("data")))
    assert ("GIN index", "plain index") in calls
