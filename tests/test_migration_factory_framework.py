"""Framework support for a testable scaffold: file-based migration discovery, the migrator/migrations
bindings on DatabaseServiceProvider, and the model Factory base."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Factory, Migration, Model, discover_migrations
from arvel.database.provider import DatabaseServiceProvider
from arvel.kernel.application import Application


def test_discover_migrations_imports_and_orders_by_filename(tmp_path: Path) -> None:
    (tmp_path / "0002_create_gadgets.py").write_text(
        "from arvel.database import Migration\n\n"
        "class CreateGadgets(Migration):\n"
        "    def up(self, schema): schema.create('gadgets', lambda t: [t.id()])\n"
        "    def down(self, schema): schema.drop('gadgets')\n"
    )
    (tmp_path / "0001_create_widgets.py").write_text(
        "from arvel.database import Migration\n\n"
        "class CreateWidgets(Migration):\n"
        "    def up(self, schema): schema.create('widgets', lambda t: [t.id()])\n"
        "    def down(self, schema): schema.drop('widgets')\n"
    )
    (tmp_path / "_helper.py").write_text("x = 1\n")  # leading underscore → skipped

    migrations = discover_migrations([str(tmp_path)])
    assert [type(m).__name__ for m in migrations] == [
        "CreateWidgets",
        "CreateGadgets",
    ]  # by filename
    assert all(isinstance(m, Migration) for m in migrations)


def test_database_provider_binds_migrator_and_discovers_migrations(tmp_path: Path) -> None:
    (tmp_path / "0001_create_things.py").write_text(
        "from arvel.database import Migration\n\n"
        "class CreateThings(Migration):\n"
        "    def up(self, schema): schema.create('things', lambda t: [t.id()])\n"
        "    def down(self, schema): schema.drop('things')\n"
    )
    app = Application(base_path=str(tmp_path))
    app.registry("database.migration_paths", list).append(
        "."
    )  # as load_migrations_from("database/migrations") would
    provider = DatabaseServiceProvider(app)
    provider.register()
    provider.boot()

    assert app.bound("migrator")
    from arvel.database import Migrator

    assert isinstance(app.make("migrator"), Migrator)
    discovered = app.make("migrations")
    assert [type(m).__name__ for m in discovered] == ["CreateThings"]


class Widget(Model):
    __fields__: ClassVar = {"name": str, "size": int}
    __fillable__: ClassVar = ["name", "size"]


class WidgetFactory(Factory[Widget]):
    model = Widget

    def definition(self) -> dict[str, Any]:
        return {"name": "default", "size": 1}


def test_factory_make_is_unsaved_with_definition_and_overrides() -> None:
    widget = WidgetFactory().make(name="custom")
    assert widget.name == "custom"  # override wins
    assert widget.size == 1  # definition default
    assert widget._exists is False  # make() does not persist

    many = WidgetFactory().make_many(3, size=9)
    assert len(many) == 3
    assert all(w.size == 9 for w in many)


async def test_factory_create_persists() -> None:
    db = ConnectionResolver()
    Widget.set_connection(db)
    await db.execute(sa.schema.CreateTable(Widget.__table__))
    try:
        created = await WidgetFactory().create(name="saved")
        assert created._exists is True
        assert created.name == "saved"
        assert len(await Widget.all()) == 1
    finally:
        await db.execute(sa.schema.DropTable(Widget.__table__))
