"""Post-ingestion extension tests for the arvel-image media-library runtime.

Edge cases beyond the basic ingestion suite:

- non-string ``file_name`` is rejected,
- ``Media.delete()`` removes derived conversion files in addition to the
  original (finer-grained than the pre-ingestion check),
- ``register_media_collections`` runs at most once per host class,
- two unrelated ``HasMedia`` subclasses do not share collections.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

pytest.importorskip("arvel_image", reason="arvel_image is the package under test")
pytest.importorskip("PIL", reason="arvel-image depends on Pillow")


if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


@pytest.fixture
def jpeg_bytes_8x8() -> bytes:
    """A small JPEG used as the source for ingestion tests."""
    from PIL import Image as PILImage

    buf = io.BytesIO()
    PILImage.new("RGB", (8, 8), (255, 0, 0)).save(buf, format="JPEG")
    return buf.getvalue()


# ─── unit ─────────────────────────────────────────────────────────────────────


def test_file_adder_rejects_non_string_file_name() -> None:
    """``sanitize_file_name`` rejects non-string input."""
    from arvel_image import MediaError
    from arvel_image.media.file_adder import FileAdder

    with pytest.raises(MediaError):
        FileAdder.sanitize_file_name(123)
    with pytest.raises(MediaError):
        FileAdder.sanitize_file_name(None)
    with pytest.raises(MediaError):
        FileAdder.sanitize_file_name(b"avatar.jpg")


# ─── integration ──────────────────────────────────────────────────────────────


async def _create_tables(engine: AsyncEngine, host_factory: Any) -> None:
    """Register the host class onto ``Model.metadata`` then run ``create_all``.

    Same pattern as the main media test helper — each test owns its host class
    so we don't accidentally share registry state across tests.
    """
    from arvel.database import Model
    from arvel_image import Media

    # Touch ``Media`` so the import is not pruned: importing the symbol
    # is what registers the ``media`` table on ``Model.metadata``.
    assert Media.__tablename__ == "media"

    host_factory()  # registers the host

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


_HOST_CACHE: dict[str, type[Any]] = {}


def _isolation_host_a() -> type[Any]:
    """Host A — declares its own ``avatar`` collection only."""
    if "IsoA" in _HOST_CACHE:
        return _HOST_CACHE["IsoA"]

    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel_image import HasMedia, MediaCollection

    class IsoA(Model, HasMedia, Timestamps):
        __tablename__ = "iso_a"

        id: int = id_()
        label: str = string(80)

        register_called: ClassVar[int] = 0

        def register_media_collections(self) -> None:
            type(self).register_called += 1
            MediaCollection("avatar", single_file=True).register_on(self)

    _HOST_CACHE["IsoA"] = IsoA
    return IsoA


def _isolation_host_b() -> type[Any]:
    """Host B — declares its own ``gallery`` collection (different from A)."""
    if "IsoB" in _HOST_CACHE:
        return _HOST_CACHE["IsoB"]

    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel_image import HasMedia, MediaCollection

    class IsoB(Model, HasMedia, Timestamps):
        __tablename__ = "iso_b"

        id: int = id_()
        label: str = string(80)

        def register_media_collections(self) -> None:
            MediaCollection("gallery").register_on(self)

    _HOST_CACHE["IsoB"] = IsoB
    return IsoB


async def test_media_delete_cascades_to_conversion_files(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes_8x8: bytes
) -> None:
    """``Media.delete()`` removes the original AND
    every recorded conversion derivative (best-effort, missing files OK).
    """
    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel.facades.storage import Storage
    from arvel_image import Conversion, HasMedia, MediaCollection
    from arvel_image.media.path_generator import DefaultPathGenerator

    class HostC(Model, HasMedia, Timestamps):
        __tablename__ = "host_c"
        id: int = id_()
        name: str = string(80)

        def register_media_collections(self) -> None:
            (
                MediaCollection("avatar", single_file=True)
                .with_conversions(
                    Conversion("thumb").fit("cover", 4, 4).format("png"),
                )
                .register_on(self)
            )

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    host = await HostC.create(name="alice")

    with Storage.fake() as ctx:
        media = await host.add_media(jpeg_bytes_8x8, file_name="x.jpg").to_media_collection(
            "avatar"
        )
        gen = DefaultPathGenerator()
        original_path = gen.path_for(media)
        thumb_path = gen.path_for_conversion(media, "thumb")

        assert ctx.fake.has_path(original_path)
        assert ctx.fake.has_path(thumb_path)
        assert media.generated_conversions.get("thumb") is True

        await media.delete()

        assert not ctx.fake.has_path(original_path)
        assert not ctx.fake.has_path(thumb_path)


async def test_register_media_collections_runs_once_per_class(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """``register_media_collections`` runs at most
    once per host class — subsequent instances reuse the registry.
    """
    HostA = _isolation_host_a()
    await _create_tables(engine, _isolation_host_a)

    a1 = await HostA.create(label="one")
    a2 = await HostA.create(label="two")

    # Trigger collection registration (lazy in collection_for).
    a1.collection_for("avatar")
    a2.collection_for("avatar")

    assert HostA.register_called == 1, (
        "register_media_collections must run once per class, not per instance"
    )


async def test_collection_per_class_isolation(engine: AsyncEngine, session: AsyncSession) -> None:
    """two unrelated HasMedia subclasses keep their own registries.

    Under strict-collection semantics, a host
    that has declared at least one collection raises
    :class:`UnknownCollectionError` for any name it didn't register —
    proof that the registries are per-class, not shared.
    """
    from arvel_image import UnknownCollectionError

    HostA = _isolation_host_a()
    HostB = _isolation_host_b()

    from arvel.database import Model

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    a = await HostA.create(label="a")
    b = await HostB.create(label="b")

    a_avatar = a.collection_for("avatar")
    b_gallery = b.collection_for("gallery")

    assert a_avatar.name == "avatar"
    assert a_avatar.single_file is True
    assert b_gallery.name == "gallery"
    assert b_gallery.single_file is False

    # B has its own registry — A's "avatar" is invisible to B.
    with pytest.raises(UnknownCollectionError):
        b.collection_for("avatar")

    # A has its own registry — B's "gallery" is invisible to A.
    with pytest.raises(UnknownCollectionError):
        a.collection_for("gallery")


async def test_media_get_path_and_temporary_url(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes_8x8: bytes
) -> None:
    """``Media.get_path`` and ``Media.get_temporary_url``
    return the disk-relative path and a time-limited URL respectively.
    """
    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel.facades.storage import Storage
    from arvel_image import HasMedia, MediaCollection

    class HostD(Model, HasMedia, Timestamps):
        __tablename__ = "host_d"
        id: int = id_()
        name: str = string(80)

        def register_media_collections(self) -> None:
            MediaCollection("avatar", single_file=True).register_on(self)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    host = await HostD.create(name="alice")

    with Storage.fake():
        media = await host.add_media(jpeg_bytes_8x8, file_name="avatar.jpg").to_media_collection(
            "avatar"
        )

        # get_path
        assert media.get_path() == f"{media.id}/avatar.jpg"
        assert media.get_path("thumb") == f"{media.id}/conversions/thumb-avatar.jpg"

        # get_temporary_url
        tmp = await media.get_temporary_url(60)
        assert tmp.startswith("memory:///")
        assert "expiry=60" in tmp


async def test_get_first_media_returns_first_or_none(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes_8x8: bytes
) -> None:
    """``get_first_media`` returns the lowest-id row or ``None``."""
    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel.facades.storage import Storage
    from arvel_image import HasMedia, MediaCollection

    class HostE(Model, HasMedia, Timestamps):
        __tablename__ = "host_e"
        id: int = id_()
        name: str = string(80)

        def register_media_collections(self) -> None:
            MediaCollection("gallery").register_on(self)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    host = await HostE.create(name="bob")

    assert await host.get_first_media("gallery") is None

    with Storage.fake():
        first = await host.add_media(jpeg_bytes_8x8, file_name="a.jpg").to_media_collection(
            "gallery"
        )
        await host.add_media(jpeg_bytes_8x8, file_name="b.jpg").to_media_collection("gallery")
        await host.add_media(jpeg_bytes_8x8, file_name="c.jpg").to_media_collection("gallery")

        got = await host.get_first_media("gallery")
        assert got is not None
        assert got.id == first.id


async def test_unknown_collection_raises_when_registry_is_strict(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes_8x8: bytes
) -> None:
    """hosts that declare collections explicitly
    raise :class:`UnknownCollectionError` for any name they didn't register.
    """
    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel.facades.storage import Storage
    from arvel_image import HasMedia, MediaCollection, UnknownCollectionError

    class HostF(Model, HasMedia, Timestamps):
        __tablename__ = "host_f"
        id: int = id_()
        name: str = string(80)

        def register_media_collections(self) -> None:
            MediaCollection("avatar", single_file=True).register_on(self)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    host = await HostF.create(name="charlie")

    with Storage.fake(), pytest.raises(UnknownCollectionError):
        await host.add_media(jpeg_bytes_8x8, file_name="x.jpg").to_media_collection("nope")


async def test_add_media_accepts_filesystem_path(
    engine: AsyncEngine,
    session: AsyncSession,
    jpeg_bytes_8x8: bytes,
    tmp_path: Any,
) -> None:
    """``add_media`` accepts a path on disk; the basename
    becomes ``Media.file_name`` when no explicit ``file_name`` is given.
    """
    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel.facades.storage import Storage
    from arvel_image import HasMedia, MediaCollection

    class HostG(Model, HasMedia, Timestamps):
        __tablename__ = "host_g"
        id: int = id_()
        name: str = string(80)

        def register_media_collections(self) -> None:
            MediaCollection("docs").register_on(self)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    src = tmp_path / "report.jpg"
    src.write_bytes(jpeg_bytes_8x8)

    host = await HostG.create(name="dave")

    with Storage.fake():
        media = await host.add_media(src).to_media_collection("docs")

    assert media.file_name == "report.jpg"
    assert media.size == len(jpeg_bytes_8x8)


async def test_add_media_accepts_file_like_object(
    engine: AsyncEngine,
    session: AsyncSession,
    jpeg_bytes_8x8: bytes,
) -> None:
    """``add_media`` accepts a file-like ``.read()`` object."""
    import io as _io

    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel.facades.storage import Storage
    from arvel_image import HasMedia, MediaCollection

    class HostH(Model, HasMedia, Timestamps):
        __tablename__ = "host_h"
        id: int = id_()
        name: str = string(80)

        def register_media_collections(self) -> None:
            MediaCollection("docs").register_on(self)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    host = await HostH.create(name="eve")
    stream = _io.BytesIO(jpeg_bytes_8x8)

    with Storage.fake():
        media = await host.add_media(stream, file_name="upload.jpg").to_media_collection("docs")

    assert media.file_name == "upload.jpg"
    assert media.size == len(jpeg_bytes_8x8)
