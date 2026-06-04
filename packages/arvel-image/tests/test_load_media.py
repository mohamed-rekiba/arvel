"""Media eager loading — the escape from a per-row N+1.

Media is a plain ``MorphMany`` relation, so the framework's own eager loading
handles it: ``.with_("media")`` on the query builder, ``load("media")`` on an
in-hand model or collection. After either, ``get_media`` serves from memory.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

import pytest

pytest.importorskip("arvel_image", reason="arvel_image is the package under test")
pytest.importorskip("PIL", reason="arvel-image depends on Pillow")

if TYPE_CHECKING:
    from typing import Self

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

_HOST_CACHE: dict[str, type[Any]] = {}


@pytest.fixture
def jpeg_bytes() -> bytes:
    from PIL import Image as PILImage

    buf = io.BytesIO()
    PILImage.new("RGB", (16, 16), (200, 100, 50)).save(buf, format="JPEG")
    return buf.getvalue()


def _host() -> type[Any]:
    if "LoadMediaHost" in _HOST_CACHE:
        return _HOST_CACHE["LoadMediaHost"]

    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel_image import HasMedia, MediaCollection

    class LoadMediaHost(HasMedia, Model, Timestamps):
        __tablename__ = "load_media_hosts"
        __media_collection__ = "gallery"

        id: int = id_()
        name: str = string(120)

        def register_media_collections(self) -> None:
            MediaCollection("gallery").register_on(self)
            MediaCollection("docs").register_on(self)

    _HOST_CACHE["LoadMediaHost"] = LoadMediaHost
    return LoadMediaHost


def _view_host() -> type[Any]:
    """A read-only host that shares another model's media via __morph_class__."""
    if "LoadMediaView" in _HOST_CACHE:
        return _HOST_CACHE["LoadMediaView"]

    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel_image import HasMedia, MediaCollection

    class LoadMediaView(HasMedia, Model, Timestamps):
        __tablename__ = "load_media_views"
        __media_collection__ = "gallery"
        # Presents as "LoadMediaHost" polymorphically — reuses its media rows.
        __morph_class__ = "LoadMediaHost"

        id: int = id_()
        name: str = string(120)

        def register_media_collections(self) -> None:
            MediaCollection("gallery").register_on(self)

    _HOST_CACHE["LoadMediaView"] = LoadMediaView
    return LoadMediaView


async def _create_tables(engine: AsyncEngine) -> None:
    import arvel_image
    from arvel.database import Model

    assert arvel_image.Media is not None
    _host()
    _view_host()
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


class _QueryCounter:
    def __init__(self, engine: AsyncEngine) -> None:
        from sqlalchemy import event

        self._engine = engine
        self._event = event
        self.count = 0

    def _before(self, *_args: object) -> None:
        self.count += 1

    def __enter__(self) -> Self:
        self._event.listen(self._engine.sync_engine, "before_cursor_execute", self._before)
        return self

    def __exit__(self, *_exc: object) -> None:
        self._event.remove(self._engine.sync_engine, "before_cursor_execute", self._before)


async def test_collection_load_serves_get_media_from_cache(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """After collection.load("media"), get_media issues zero queries per host."""
    from arvel.database.collection import ModelCollection
    from arvel.facades import Storage

    await _create_tables(engine)
    host_cls = _host()
    hosts = [await host_cls.create(name=f"h{i}") for i in range(5)]
    with Storage.fake():
        for host in hosts:
            await host.add_image(jpeg_bytes, file_name="a.jpg")

        await ModelCollection(hosts).load("media")

        with _QueryCounter(engine) as counter:
            for host in hosts:
                media = host.get_media()
                assert len(media) == 1
        assert counter.count == 0, "get_media must serve from the eager cache, not the DB"


async def test_collection_load_batches_into_a_single_query(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """Loading N same-type hosts costs one query, not N."""
    from arvel.database.collection import ModelCollection
    from arvel.facades import Storage

    await _create_tables(engine)
    host_cls = _host()
    hosts = [await host_cls.create(name=f"b{i}") for i in range(6)]
    with Storage.fake():
        for host in hosts:
            await host.add_image(jpeg_bytes, file_name="a.jpg")

        with _QueryCounter(engine) as counter:
            await ModelCollection(hosts).load("media")
        assert counter.count == 1, f"expected one batched query, got {counter.count}"


async def test_cached_reads_filter_by_collection(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """Cached reads still respect the requested collection."""
    from arvel.facades import Storage

    await _create_tables(engine)
    host_cls = _host()
    host = await host_cls.create(name="mixed")
    with Storage.fake():
        await host.add_image(jpeg_bytes, file_name="g.jpg")
        await host.add_image(jpeg_bytes, file_name="d.jpg", collection="docs")

        await host.load("media")
        with _QueryCounter(engine) as counter:
            gallery = host.get_media()
            docs = host.media_in("docs")
        assert counter.count == 0
        assert {m.collection_name for m in gallery} == {"gallery"}
        assert {m.collection_name for m in docs} == {"docs"}


async def test_add_image_invalidates_eager_cache(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """Adding media after a preload must not serve a stale cached list."""
    from arvel.facades import Storage

    await _create_tables(engine)
    host_cls = _host()
    host = await host_cls.create(name="grows")
    with Storage.fake():
        await host.add_image(jpeg_bytes, file_name="one.jpg")
        await host.load("media")

        await host.add_image(jpeg_bytes, file_name="two.jpg")
        media = host.get_media()
        assert len(media) == 2, "add_image must keep the eager cache in sync"


async def test_with_media_query_builder_feeds_get_media(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """The idiomatic `.with_("media")` eager load is honored by get_media."""
    from arvel.facades import Storage

    await _create_tables(engine)
    host_cls = _host()
    hosts = [await host_cls.create(name=f"w{i}") for i in range(4)]
    with Storage.fake():
        for host in hosts:
            await host.add_image(jpeg_bytes, file_name="a.jpg")

        loaded = list(await host_cls.with_("media").get())

        with _QueryCounter(engine) as counter:
            for host in loaded:
                media = host.get_media()
                assert len(media) == 1
        assert counter.count == 0, "get_media must read the .with_('media') eager cache"


async def test_with_media_honors_morph_class_redirect(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """`.with_("media")` on a __morph_class__ view model loads the canonical rows.

    The view presents as "LoadMediaHost" polymorphically, so its `media` relation
    batches against the shared rows and get_media serves them with zero extra queries.
    """
    from arvel.facades import Storage

    await _create_tables(engine)
    host_cls = _host()
    view_cls = _view_host()
    with Storage.fake():
        host = await host_cls.create(name="canonical")
        await host.add_image(jpeg_bytes, file_name="a.jpg")
        # Same id as the canonical host — the view reuses its media rows.
        view = await view_cls.create(name="view")
        assert view.id == host.id

        loaded = list(await view_cls.with_("media").get())

        with _QueryCounter(engine) as counter:
            for row in loaded:
                media = row.get_media()
                assert len(media) == 1
        assert counter.count == 0, ".with_('media') must honor __morph_class__"


async def test_view_model_writes_media_under_canonical_type(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """A __morph_class__ host stores media rows under the canonical type, not its own.

    Guards the read/write symmetry: get_morph_alias drives both, so a row added
    through the view is visible to the canonical host and vice versa.
    """
    from arvel.facades import Storage

    await _create_tables(engine)
    host_cls = _host()
    view_cls = _view_host()
    with Storage.fake():
        host = await host_cls.create(name="canonical")
        view = await view_cls.create(name="view")
        assert view.id == host.id

        await view.add_image(jpeg_bytes, file_name="v.jpg")

        # The canonical host sees the row the view wrote.
        await host.load("media")
        canonical_media = host.get_media()
        assert len(canonical_media) == 1
        assert canonical_media[0].model_type == "LoadMediaHost"
