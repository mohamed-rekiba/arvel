"""Search (05-SEARCH-SCOUT) — the fluent builder + `scout:import`/`scout:flush` against a real
Meilisearch server: index+search+filter+sort+paginate round-trip, bulk import/flush, and the
async-correctness fix (every Meilisearch call runs off the event loop, in a worker thread)."""

from __future__ import annotations

import contextlib
from typing import Any, ClassVar

import pytest
import sqlalchemy as sa
from typer.testing import CliRunner

from arvel.console import build_cli
from arvel.database import ConnectionResolver, Model, SoftDeletes
from arvel.search import MeilisearchEngine, Searchable, SearchManager

pytestmark = pytest.mark.integration

runner = CliRunner()


class MeiliArticle(Searchable, Model):
    __table_name__ = "meili_articles"
    __fields__: ClassVar = {"title": str, "kind": str, "views": int}
    __fillable__: ClassVar = ["title", "kind", "views"]

    @classmethod
    def searchable_filterable(cls) -> list[str]:
        return ["kind"]

    @classmethod
    def searchable_sortable(cls) -> list[str]:
        return ["views"]


async def _boot(configure_app: Any, meilisearch_url: dict[str, str]) -> ConnectionResolver:
    app = configure_app(
        search={
            "driver": "meilisearch",
            "meilisearch": {"url": meilisearch_url["url"], "key": meilisearch_url["key"]},
        }
    )
    app.singleton("search", lambda a: SearchManager(a))
    db = ConnectionResolver()
    MeiliArticle.set_connection(db)
    await db.execute(sa.schema.CreateTable(MeiliArticle.__table__))
    # a fresh index per test: the container (and its data) is reused across the whole session.
    # best-effort: a brand-new index that Meilisearch hasn't created yet fails to flush.
    with contextlib.suppress(Exception):
        await app.make("search").flush(MeiliArticle.searchable_as())
    # `where`/`order_by` only work on Meilisearch once the field is declared filterable/sortable
    # (scout:import does this too — pushed here so the plain save/search tests don't need the CLI).
    await app.make("search").configure(
        MeiliArticle.searchable_as(),
        filterable=MeiliArticle.searchable_filterable(),
        sortable=MeiliArticle.searchable_sortable(),
    )
    return db


async def test_index_search_filter_sort_paginate_round_trip(
    configure_app: Any, meilisearch_url: dict[str, str]
) -> None:
    db = await _boot(configure_app, meilisearch_url)
    try:
        await MeiliArticle.create(title="python one", kind="post", views=3)
        await MeiliArticle.create(title="python two", kind="post", views=1)
        await MeiliArticle.create(title="python three", kind="post", views=2)
        await MeiliArticle.create(title="ruby page", kind="page", views=9)

        hits = (
            await MeiliArticle.search("python").where("kind", "post").order_by("views", "asc").get()
        )
        assert [h.title for h in hits] == ["python two", "python three", "python one"]

        page = (
            await MeiliArticle.search("python")
            .where("kind", "post")
            .order_by("views", "asc")
            .paginate(per_page=2, page=1)
        )
        assert page.total() == 3
        assert [a.views for a in page.items()] == [1, 2]

        first = await MeiliArticle.search("ruby").first()
        assert first is not None and first.title == "ruby page"
    finally:
        await db.dispose()


async def test_save_updates_the_index_and_delete_removes_it(
    configure_app: Any, meilisearch_url: dict[str, str]
) -> None:
    db = await _boot(configure_app, meilisearch_url)
    try:
        article = await MeiliArticle.create(title="async python", kind="post", views=1)
        assert len(await MeiliArticle.search("async").get()) == 1

        await article.delete()
        assert await MeiliArticle.search("async").get() == []
    finally:
        await db.dispose()


class MeiliNote(Searchable, Model, SoftDeletes):
    __table_name__ = "meili_notes"
    __fields__: ClassVar = {"title": str}
    __fillable__: ClassVar = ["title"]

    @classmethod
    def searchable_filterable(cls) -> list[str]:
        return ["__soft_deleted"]


async def test_soft_delete_model_keeps_trashed_docs_reachable_via_with_trashed(
    configure_app: Any, meilisearch_url: dict[str, str]
) -> None:
    """search.soft_delete=True against a real Meilisearch server: a soft-deleted row stays
    indexed (flagged), excluded by default, reachable via with_trashed()/only_trashed()."""
    app = configure_app(
        search={
            "driver": "meilisearch",
            "soft_delete": True,
            "meilisearch": {"url": meilisearch_url["url"], "key": meilisearch_url["key"]},
        }
    )
    app.singleton("search", lambda a: SearchManager(a))
    db = ConnectionResolver()
    MeiliNote.set_connection(db)
    await db.execute(sa.schema.CreateTable(MeiliNote.__table__))
    with contextlib.suppress(Exception):
        await app.make("search").flush(MeiliNote.searchable_as())
    await app.make("search").configure(
        MeiliNote.searchable_as(), filterable=MeiliNote.searchable_filterable(), sortable=[]
    )
    try:
        note = await MeiliNote.create(title="secret note")
        await note.delete()  # soft — kept indexed, flagged

        assert await MeiliNote.search("secret").get() == []
        assert [n.title for n in await MeiliNote.search("secret").with_trashed().get()] == [
            "secret note"
        ]
        assert [n.title for n in await MeiliNote.search("secret").only_trashed().get()] == [
            "secret note"
        ]

        await note.restore()
        assert [n.title for n in await MeiliNote.search("secret").get()] == ["secret note"]
    finally:
        await db.dispose()


def test_scout_import_count_parity_and_scout_flush_empties(
    configure_app: Any, meilisearch_url: dict[str, str]
) -> None:
    """A plain (non-async) test: `scout:import`/`scout:flush` run through the full CLI dispatch
    (``run_app_command`` → its own ``asyncio.run``), which can't nest inside an already-running
    loop — so, unlike the other tests here, the async setup/assertions run via explicit
    ``asyncio.run`` calls around the synchronous ``runner.invoke``s, unnested."""
    import asyncio

    from arvel.kernel import app as active_app

    async def _seed() -> tuple[ConnectionResolver, int]:
        db = await _boot(configure_app, meilisearch_url)
        for n in range(5):
            await MeiliArticle.create(title=f"row {n}", kind="post", views=n)
        row_count = await MeiliArticle.count()
        # clear whatever auto-sync already wrote, so scout:import's own count is what's asserted
        await active_app("search").flush(MeiliArticle.searchable_as())
        return db, row_count

    db, row_count = asyncio.run(_seed())
    try:
        assert row_count == 5

        result = runner.invoke(build_cli(), ["scout:import", f"{__name__}:MeiliArticle"])
        assert result.exit_code == 0, result.output
        assert f"scout:import complete: {row_count} record(s)" in result.output

        async def _engine_total() -> int:
            return (await MeiliArticle.search("row").raw()).total

        assert asyncio.run(_engine_total()) == row_count  # post-import count == row count

        flush_result = runner.invoke(build_cli(), ["scout:flush", f"{__name__}:MeiliArticle"])
        assert flush_result.exit_code == 0, flush_result.output

        async def _remaining() -> list[Any]:
            return await MeiliArticle.search("row").get()

        assert asyncio.run(_remaining()) == []
    finally:
        asyncio.run(db.dispose())


async def test_meilisearch_calls_never_block_the_event_loop(
    meilisearch_url: dict[str, str],
) -> None:
    """The async-correctness fix (spec §2): every engine call runs in a worker thread — proven by
    a concurrent asyncio task making progress *while* a Meilisearch call is in flight."""
    import asyncio

    engine = MeilisearchEngine(url=meilisearch_url["url"], key=meilisearch_url["key"])
    index = "loop_liveness"
    ticks: list[int] = []

    async def _ticker() -> None:
        for i in range(50):
            ticks.append(i)
            await asyncio.sleep(0.001)

    ticker_task = asyncio.create_task(_ticker())
    for n in range(20):
        await engine.index(index, n, {"n": n})
    await ticker_task

    assert len(ticks) == 50, "the ticker starved — a sync call is blocking the event loop"
    await engine.flush(index)
