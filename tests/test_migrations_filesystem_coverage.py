"""Coverage — migration Schema ops (execute/create_view) + filesystem manager (docs 08/16)."""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver
from arvel.database.migrations import Migration, Migrator, Schema
from arvel.filesystem import Filesystem, FilesystemManager


class CreateStuff(Migration):
    def up(self, schema: Schema) -> None:
        schema.create("stuff", lambda t: [t.id(), t.string("name")])
        schema.execute(sa.text("INSERT INTO stuff (name) VALUES ('x')"))
        schema.create_view("stuff_view", "SELECT name FROM stuff")

    def down(self, schema: Schema) -> None:
        schema.execute(sa.text("DROP VIEW IF EXISTS stuff_view"))
        schema.drop("stuff")


async def test_migration_schema_execute_and_view() -> None:
    db = ConnectionResolver()
    migrator = Migrator(db)
    try:
        await migrator.run([CreateStuff()])
        rows = await db.select("SELECT name FROM stuff_view")
        assert rows[0]["name"] == "x"
        await migrator.rollback([CreateStuff()])
    finally:
        await db.dispose()


def test_migration_base_methods_raise() -> None:
    with pytest.raises(NotImplementedError):
        Migration().up(None)  # type: ignore[arg-type]
    with pytest.raises(NotImplementedError):
        Migration().down(None)  # type: ignore[arg-type]


def test_filesystem_manager_local_disk() -> None:
    assert isinstance(FilesystemManager().disk(), Filesystem)


def test_filesystem_default_driver_from_config() -> None:
    class App:
        def config(self, key: str, default: Any = None) -> Any:
            return "local"

    assert FilesystemManager(App()).default_driver() == "local"
