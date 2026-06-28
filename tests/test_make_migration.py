"""make:migration — timestamped migration generator (Laravel artisan parity). ``create_X_table``
names get a create/drop stub; other names get a generic up/down stub. The generated create migration
is proven functional: it actually creates and drops the table through the real Migrator."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa

from arvel.console.generators import generate_migration


def _load(path: Path, modname: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(modname, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # executes `from arvel.database import Migration`
    return module


def test_create_table_stub(tmp_path: Path) -> None:
    target = generate_migration("create_posts_table", base=tmp_path)
    assert target.parent == tmp_path / "database" / "migrations"
    assert re.fullmatch(r"\d{4}_\d{2}_\d{2}_\d{6}_create_posts_table\.py", target.name)
    src = target.read_text()
    assert "class CreatePostsTable(Migration)" in src
    assert 'schema.create("posts", define)' in src
    assert 'schema.drop("posts")' in src
    assert hasattr(_load(target, "m_create"), "CreatePostsTable")


def test_generic_stub_for_non_create_names(tmp_path: Path) -> None:
    target = generate_migration("add_status_to_posts", base=tmp_path)
    assert target.name.endswith("_add_status_to_posts.py")
    src = target.read_text()
    assert "class AddStatusToPosts(Migration)" in src
    assert "schema.create" not in src  # not a create_*_table → generic up/down only
    assert hasattr(_load(target, "m_generic"), "AddStatusToPosts")


async def test_generated_create_migration_actually_runs(tmp_path: Path) -> None:
    from arvel.database import ConnectionResolver
    from arvel.database.migrations import Migrator

    target = generate_migration("create_widgets_table", base=tmp_path)
    migration = _load(target, "m_run").CreateWidgetsTable()
    db = ConnectionResolver()
    try:
        await Migrator(db).run([migration])  # the real migration path
        async with db.engine().connect() as conn:
            tables = await conn.run_sync(lambda c: sa.inspect(c).get_table_names())
        assert "widgets" in tables  # up() created it
        await Migrator(db).rollback([migration])
        async with db.engine().connect() as conn:
            tables = await conn.run_sync(lambda c: sa.inspect(c).get_table_names())
        assert "widgets" not in tables  # down() dropped it
    finally:
        await db.dispose()
