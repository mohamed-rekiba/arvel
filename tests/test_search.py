"""arvel.search — Scout-style search module: ArrayEngine, SearchManager driver resolution, the
Searchable mixin (auto-sync on save/delete + Model.search hydration), the fluent SearchBuilder
(where/order_by/take/get/first/paginate/keys/raw), and the queued-indexing seam."""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model, SoftDeletes
from arvel.events import Dispatcher
from arvel.kernel import set_application
from arvel.kernel.application import Application
from arvel.search import ArrayEngine, ModelIndexRequested, Searchable, SearchManager, SearchResult
from arvel.search.listeners import handle_index_request
from arvel.support.manager import MissingExtraError


class Article(Searchable, Model):  # Searchable BEFORE Model so its _fire override wins (MRO)
    __fields__ = {"title": str, "body": str, "views": int}
    __fillable__ = ["title", "body", "views"]


# --- ArrayEngine -----------------------------------------------------------
async def test_array_engine_index_search_delete() -> None:
    engine = ArrayEngine()
    await engine.index("articles", 1, {"title": "async python", "body": "fast web"})
    await engine.index("articles", 2, {"title": "ruby on rails", "body": "slow"})
    assert len((await engine.search("articles", "python")).hits) == 1
    assert len((await engine.search("articles", "SLOW")).hits) == 1  # case-insensitive
    await engine.delete("articles", 1)
    assert (await engine.search("articles", "python")).hits == []


async def test_array_engine_search_returns_a_search_result_with_key_and_total() -> None:
    engine = ArrayEngine()
    await engine.index("articles", 7, {"title": "async python"})
    result = await engine.search("articles", "python")
    assert isinstance(result, SearchResult)
    assert result.total == 1
    assert result.hits[0]["_key"] == 7
    assert result.hits[0]["title"] == "async python"


async def test_array_engine_filters_sorts_and_slices() -> None:
    engine = ArrayEngine()
    await engine.index("articles", 1, {"kind": "post", "n": 3})
    await engine.index("articles", 2, {"kind": "post", "n": 1})
    await engine.index("articles", 3, {"kind": "post", "n": 2})
    await engine.index("articles", 4, {"kind": "page", "n": 9})

    result = await engine.search("articles", "", filters={"kind": "post"}, sort=["n:asc"])
    assert [h["_key"] for h in result.hits] == [2, 3, 1]
    assert result.total == 3  # total is the filtered count, before any limit/offset slice

    page = await engine.search(
        "articles", "", filters={"kind": "post"}, sort=["n:asc"], limit=1, offset=1
    )
    assert [h["_key"] for h in page.hits] == [3]
    assert page.total == 3


async def test_array_engine_configure_is_a_no_op() -> None:
    engine = ArrayEngine()
    await engine.configure("articles", filterable=["kind"], sortable=["n"])  # doesn't raise


# --- SearchManager ---------------------------------------------------------
def test_manager_default_is_array() -> None:
    assert isinstance(SearchManager().driver(), ArrayEngine)


def test_manager_unknown_driver_raises_missing_extra() -> None:
    with pytest.raises(MissingExtraError):
        SearchManager().driver("algolia")  # no such driver / extra installed


# --- Searchable mixin (auto-sync + search) ---------------------------------
async def _app_with_search() -> tuple[Application, ConnectionResolver]:
    app = Application.configure().with_config({"search": {"driver": "array"}}).create()
    app.singleton("search", lambda a: SearchManager(a))
    db = ConnectionResolver()
    Article.set_connection(db)
    await db.execute(sa.schema.CreateTable(Article.__table__))
    return app, db


async def test_save_indexes_and_search_hydrates_models() -> None:
    _app, db = await _app_with_search()
    try:
        await Article.create(title="async python", body="fast web", views=1)
        await Article.create(title="ruby on rails", body="slow", views=2)
        hits = await Article.search("python").get()
        assert [h.title for h in hits] == ["async python"]
        assert isinstance(hits[0], Article)  # hydrated model
    finally:
        await db.dispose()


async def test_make_all_searchable_bulk_indexes_and_remove_all_flushes() -> None:
    _app, db = await _app_with_search()
    try:
        # rows inserted with indexing suppressed (raw) still get indexed by make_all_searchable
        await Article.create(title="async python", body="fast web", views=1)
        await Article.create(title="ruby on rails", body="slow", views=2)
        indexed = await Article.make_all_searchable()
        assert indexed == 2
        assert {h.title for h in await Article.search("async").get()} == {"async python"}
        await Article.remove_all_from_search()
        assert await Article.search("async").get() == []
    finally:
        await db.dispose()


async def test_delete_removes_from_index() -> None:
    _app, db = await _app_with_search()
    try:
        article = await Article.create(title="async python", body="fast web", views=1)
        assert len(await Article.search("python").get()) == 1
        await article.delete()
        assert await Article.search("python").get() == []
    finally:
        await db.dispose()


async def test_restore_reindexes_a_soft_deleted_model() -> None:
    """Scout parity: soft-delete unsearches a model; restore re-indexes it via the `restored` hook."""

    class Post(Searchable, Model, SoftDeletes):
        __fields__ = {"title": str}
        __fillable__ = ["title"]

    _app, db = await _app_with_search()
    try:
        Post.set_connection(db)
        await db.execute(sa.schema.CreateTable(Post.__table__))
        post = await Post.create(title="hidden gem")
        assert len(await Post.search("gem").get()) == 1
        await post.delete()  # soft — fires deleted → unsearchable
        assert await Post.search("gem").get() == []
        await post.restore()  # fires restored → searchable again
        assert {h.title for h in await Post.search("gem").get()} == {"hidden gem"}
    finally:
        Post.set_connection(None)
        await db.dispose()


async def test_searchable_metadata_defaults() -> None:
    assert Article.searchable_as() == "articles"
    assert Article.searchable_filterable() == []
    assert Article.searchable_sortable() == []
    article = Article(title="x", body="y", views=0)
    article.id = 7
    assert article.get_search_key() == 7
    assert article.to_searchable_array()["title"] == "x"


# --- SearchBuilder: where / order_by / take / first / paginate / keys / raw ------------
async def test_builder_where_filters_and_order_by_sorts() -> None:
    _app, db = await _app_with_search()
    try:
        await Article.create(title="python one", body="x", views=3)
        await Article.create(title="python two", body="x", views=1)
        await Article.create(title="python three", body="x", views=2)
        await Article.create(title="ruby", body="x", views=9)

        hits = await Article.search("python").where("body", "x").order_by("views", "asc").get()
        assert [h.title for h in hits] == ["python two", "python three", "python one"]
    finally:
        await db.dispose()


async def test_builder_take_caps_results() -> None:
    _app, db = await _app_with_search()
    try:
        for n in range(5):
            await Article.create(title="python", body=f"b{n}", views=n)
        hits = await Article.search("python").take(2).get()
        assert len(hits) == 2
    finally:
        await db.dispose()


async def test_builder_first_returns_one_or_none() -> None:
    _app, db = await _app_with_search()
    try:
        assert await Article.search("python").first() is None
        await Article.create(title="python", body="x", views=1)
        first = await Article.search("python").first()
        assert first is not None and first.title == "python"
    finally:
        await db.dispose()


async def test_builder_keys_returns_raw_engine_keys_unhydrated() -> None:
    _app, db = await _app_with_search()
    try:
        a = await Article.create(title="python", body="x", views=1)
        keys = await Article.search("python").keys()
        assert keys == [a.id]
    finally:
        await db.dispose()


async def test_builder_raw_returns_the_engine_search_result() -> None:
    _app, db = await _app_with_search()
    try:
        await Article.create(title="python", body="x", views=1)
        raw = await Article.search("python").raw()
        assert isinstance(raw, SearchResult)
        assert raw.total == 1
        assert raw.hits[0]["title"] == "python"
    finally:
        await db.dispose()


async def test_builder_paginate_returns_a_length_aware_paginator() -> None:
    from arvel.pagination import LengthAwarePaginator

    _app, db = await _app_with_search()
    try:
        for n in range(5):
            await Article.create(title="python", body=f"b{n}", views=n)
        page = await Article.search("python").order_by("views", "asc").paginate(per_page=2, page=1)
        assert isinstance(page, LengthAwarePaginator)
        assert page.total() == 5
        assert page.per_page() == 2
        assert page.last_page() == 3
        assert [a.views for a in page.items()] == [0, 1]

        page2 = await Article.search("python").order_by("views", "asc").paginate(per_page=2, page=2)
        assert [a.views for a in page2.items()] == [2, 3]
    finally:
        await db.dispose()


async def test_builder_hydration_preserves_engine_order() -> None:
    """Hydration is a `whereIn(pk, keys)` fetch — DB return order isn't guaranteed to match, so the
    builder must reorder to the engine's hit order (here, descending views)."""
    _app, db = await _app_with_search()
    try:
        first = await Article.create(title="python", body="x", views=1)
        second = await Article.create(title="python", body="x", views=2)
        third = await Article.create(title="python", body="x", views=3)

        hits = await Article.search("python").order_by("views", "desc").get()
        assert [h.id for h in hits] == [third.id, second.id, first.id]
    finally:
        await db.dispose()


async def test_builder_excludes_soft_deleted_unless_with_trashed() -> None:
    class Note(Searchable, Model, SoftDeletes):
        __fields__ = {"title": str}
        __fillable__ = ["title"]

    app, db = await _app_with_search()
    try:
        Note.set_connection(db)
        await db.execute(sa.schema.CreateTable(Note.__table__))
        note = await Note.create(title="secret note")
        await note.delete()  # soft-delete; the `deleted` hook already ran unsearchable()

        # simulate a still-present (e.g. stale) index entry for the trashed row, to prove it's the
        # *hydration* query's default scope excluding it — not just the index having been cleared:
        engine = app.make("search")
        await engine.index(Note.searchable_as(), note.id, note.to_searchable_array())

        assert await Note.search("secret").get() == []
        trashed = await Note.search("secret").with_trashed().get()
        assert [t.title for t in trashed] == ["secret note"]
    finally:
        Note.set_connection(None)
        await db.dispose()


# --- Queued-indexing seam ---------------------------------------------------
class _SpyEngine:
    """Wraps ``ArrayEngine``, recording every write call — proves queued mode skips them."""

    def __init__(self) -> None:
        self.inner = ArrayEngine()
        self.index_calls: list[tuple[Any, Any]] = []
        self.delete_calls: list[Any] = []

    async def index(self, index: str, key: Any, record: dict[str, Any]) -> None:
        self.index_calls.append((index, key))
        await self.inner.index(index, key, record)

    async def delete(self, index: str, key: Any) -> None:
        self.delete_calls.append(key)
        await self.inner.delete(index, key)

    async def search(self, index: str, query: str, **kwargs: Any) -> SearchResult:
        return await self.inner.search(index, query, **kwargs)

    async def flush(self, index: str) -> None:
        await self.inner.flush(index)

    async def configure(self, index: str, *, filterable: Any, sortable: Any) -> None:
        pass


async def _app_with_queued_search(spy: _SpyEngine) -> tuple[Application, ConnectionResolver]:
    config = {"search": {"driver": "array", "queue": True}}
    app = Application.configure().with_config(config).create()
    app.instance("search", spy)
    app.instance("events", Dispatcher())
    db = ConnectionResolver()
    Article.set_connection(db)
    await db.execute(sa.schema.CreateTable(Article.__table__))
    return app, db


async def test_queued_mode_emits_an_event_and_skips_the_inline_write() -> None:
    spy = _SpyEngine()
    _app, db = await _app_with_queued_search(spy)
    try:
        await Article.create(title="python", body="x", views=1)
        assert spy.index_calls == []  # no inline write happened
        assert await Article.search("python").get() == []  # the index is still empty
    finally:
        await db.dispose()


async def test_queued_mode_dispatches_model_index_requested_with_the_record() -> None:
    spy = _SpyEngine()
    _app, db = await _app_with_queued_search(spy)
    captured: list[ModelIndexRequested] = []
    _app.make("events").listen(ModelIndexRequested, captured.append)
    try:
        article = await Article.create(title="python", body="x", views=1)
        assert len(captured) == 1
        event = captured[0]
        assert event.model_class is Article
        assert event.key == article.id
        assert event.record is not None and event.record["title"] == "python"

        await article.delete()
        assert len(captured) == 2
        assert captured[1].record is None  # delete -> record=None
    finally:
        await db.dispose()


async def test_sync_mode_is_still_the_default_and_writes_inline() -> None:
    spy = _SpyEngine()
    app = Application.configure().with_config({"search": {"driver": "array"}}).create()
    app.instance("search", spy)
    db = ConnectionResolver()
    Article.set_connection(db)
    await db.execute(sa.schema.CreateTable(Article.__table__))
    try:
        await Article.create(title="python", body="x", views=1)
        assert spy.index_calls != []
    finally:
        await db.dispose()


# --- listeners.handle_index_request (the queued seam's proof listener) -----
async def test_handle_index_request_indexes_when_record_is_present() -> None:
    spy = _SpyEngine()
    app = Application()
    app.instance("search", spy)
    set_application(app)
    try:
        event = ModelIndexRequested(Article, 1, {"title": "queued write"})
        await handle_index_request(event)
        assert spy.index_calls == [("articles", 1)]
        assert (await spy.inner.search("articles", "queued")).total == 1
    finally:
        set_application(None)


async def test_handle_index_request_deletes_when_record_is_none() -> None:
    spy = _SpyEngine()
    await spy.index("articles", 1, {"title": "will be removed"})
    app = Application()
    app.instance("search", spy)
    set_application(app)
    try:
        await handle_index_request(ModelIndexRequested(Article, 1, None))
        assert spy.delete_calls == [1]
    finally:
        set_application(None)


async def test_handle_index_request_is_a_no_op_without_a_bound_engine() -> None:
    set_application(Application())
    try:
        await handle_index_request(ModelIndexRequested(Article, 1, {"title": "x"}))  # no raise
    finally:
        set_application(None)


def test_meilisearch_filter_field_must_be_a_bare_identifier() -> None:
    from arvel.search import _safe_field

    assert _safe_field("views") == "views"
    assert _safe_field("meta.rank") == "meta.rank"
    import pytest

    for bad in ("views = 1 OR title = 'x'", "views;drop", "a b", "1abc"):
        with pytest.raises(ValueError):
            _safe_field(bad)


async def test_queued_mode_without_a_dispatcher_raises_instead_of_dropping_the_write() -> None:
    # search.queue on but no events binding: a silent skip would lose the index write, so fail loud
    spy = _SpyEngine()
    config = {"search": {"driver": "array", "queue": True}}
    app = Application.configure().with_config(config).create()
    app.instance("search", spy)
    db = ConnectionResolver()
    Article.set_connection(db)
    await db.execute(sa.schema.CreateTable(Article.__table__))
    try:
        import pytest

        with pytest.raises(RuntimeError, match="no event dispatcher"):
            await Article.create(title="python", body="x", views=1)
    finally:
        await db.dispose()
