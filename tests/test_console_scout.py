"""Console (05-SEARCH-SCOUT) — `scout:import`/`scout:flush` bulk-index/empty a searchable
model's index, resolving MODEL by a dotted `module:ClassName` path or its bare class name."""

from __future__ import annotations

from typing import ClassVar

import sqlalchemy as sa
from typer.testing import CliRunner

from arvel.console import build_cli
from arvel.database import ConnectionResolver, Model
from arvel.kernel import Application, set_application
from arvel.search import Searchable, SearchManager

runner = CliRunner()


class ScoutArticle(Searchable, Model):  # Searchable BEFORE Model so its _fire override wins (MRO)
    __table_name__ = "scout_articles"
    __fields__: ClassVar = {"title": str}
    __fillable__: ClassVar = ["title"]


async def _seed(app: Application, count: int) -> ConnectionResolver:
    db = ConnectionResolver()
    ScoutArticle.set_connection(db)
    await db.execute(sa.schema.CreateTable(ScoutArticle.__table__))
    for n in range(count):
        await ScoutArticle.create(title=f"article {n}")
    app.instance("db", db)
    return db


def test_scout_import_without_engine_errors() -> None:
    set_application(Application())  # active app, but no 'search' bound
    try:
        result = runner.invoke(build_cli(), ["scout:import", f"{__name__}:ScoutArticle"])
        assert result.exit_code == 1
        assert "no search engine bound" in result.output
    finally:
        set_application(None)


def test_scout_import_bad_dotted_path_errors() -> None:
    set_application(Application())
    try:
        result = runner.invoke(build_cli(), ["scout:import", f"{__name__}:NoSuchModel"])
        assert result.exit_code != 0
        assert "no attribute" in result.output
    finally:
        set_application(None)


def test_scout_import_indexes_every_row_via_a_dotted_path() -> None:
    import asyncio

    app = Application.configure().with_config({"search": {"driver": "array"}}).create()
    app.singleton("search", lambda a: SearchManager(a))
    set_application(app)
    try:
        asyncio.run(_seed(app, 3))
        result = runner.invoke(build_cli(), ["scout:import", f"{__name__}:ScoutArticle"])
        assert result.exit_code == 0, result.output
        assert "scout:import complete: 3 record(s)" in result.output

        async def _count() -> int:
            return len(await ScoutArticle.search("article").get())

        assert asyncio.run(_count()) == 3
    finally:
        set_application(None)


def test_scout_import_resolves_a_bare_model_name() -> None:
    import asyncio

    app = Application.configure().with_config({"search": {"driver": "array"}}).create()
    app.singleton("search", lambda a: SearchManager(a))
    set_application(app)
    try:
        asyncio.run(_seed(app, 2))
        result = runner.invoke(build_cli(), ["scout:import", "ScoutArticle"])
        assert result.exit_code == 0, result.output
        assert "scout:import complete: 2 record(s)" in result.output
    finally:
        set_application(None)


def test_scout_flush_empties_the_index() -> None:
    import asyncio

    app = Application.configure().with_config({"search": {"driver": "array"}}).create()
    app.singleton("search", lambda a: SearchManager(a))
    set_application(app)
    try:
        asyncio.run(_seed(app, 2))
        assert (
            runner.invoke(build_cli(), ["scout:import", f"{__name__}:ScoutArticle"]).exit_code == 0
        )

        result = runner.invoke(build_cli(), ["scout:flush", f"{__name__}:ScoutArticle"])
        assert result.exit_code == 0, result.output
        assert "flushed 'scout_articles'" in result.output

        async def _count() -> int:
            return len(await ScoutArticle.search("article").get())

        assert asyncio.run(_count()) == 0
    finally:
        set_application(None)
