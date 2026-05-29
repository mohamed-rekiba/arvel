"""QA-Pre tests for WI-arvel-050 — arvel-image medialibrary v11 parity (Round 2).

Maps to PRD-050 FRs FR-050-01 .. FR-050-29.

All tests in this file are expected to FAIL until Stage 3b (Execution) implements
the corresponding features. They compile and the infrastructure runs; the assertions
fail because the features do not yet exist.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

import pytest

pytest.importorskip("arvel_image", reason="arvel_image is the package under test")
pytest.importorskip("PIL", reason="arvel-image depends on Pillow")

from sqlalchemy.orm import Mapped

if TYPE_CHECKING:
    from arvel_image.media.model import Media
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

# ─── Shared fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def jpeg_bytes() -> bytes:
    from PIL import Image as PILImage

    buf = io.BytesIO()
    PILImage.new("RGB", (16, 16), (200, 100, 50)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def png_bytes() -> bytes:
    from PIL import Image as PILImage

    buf = io.BytesIO()
    PILImage.new("RGBA", (8, 8), (0, 200, 0, 255)).save(buf, format="PNG")
    return buf.getvalue()


# ─── Host model factory ───────────────────────────────────────────────────────

_HOST_CACHE_050: dict[str, type[Any]] = {}


async def _create_tables_050(engine: AsyncEngine) -> None:
    import arvel_image  # ensure Media table is registered
    from arvel.database import Model

    assert arvel_image.Media is not None
    _host_050()
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


def _host_050() -> type[Any]:
    if "Host050" in _HOST_CACHE_050:
        return _HOST_CACHE_050["Host050"]

    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel_image import HasMedia, MediaCollection

    class Host050(Model, HasMedia, Timestamps):
        __tablename__ = "media_050_hosts"

        id: Mapped[int] = id_()
        name: Mapped[str] = string(120)

        def register_media_collections(self) -> None:
            MediaCollection("avatar", single_file=True).register_on(self)
            MediaCollection("gallery").register_on(self)
            MediaCollection("docs").register_on(self)

    _HOST_CACHE_050["Host050"] = Host050
    return Host050


def _host_custom_pk_050() -> type[Any]:
    """Host that overrides host_pk() to return 'custom-{id}'."""
    if "HostCustomPk050" in _HOST_CACHE_050:
        return _HOST_CACHE_050["HostCustomPk050"]

    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel_image import HasMedia

    class HostCustomPk050(Model, HasMedia, Timestamps):
        __tablename__ = "media_050_custom_pk_hosts"

        id: Mapped[int] = id_()
        name: Mapped[str] = string(120)

        def host_pk(self) -> str:
            return f"custom-{self.id}"

    _HOST_CACHE_050["HostCustomPk050"] = HostCustomPk050
    return HostCustomPk050


# ─── FR-050-01/02/03: regenerate() no-args + disk resolution ─────────────────


async def test_regenerate_no_args_processes_all_rows(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-01: regenerate() with no arguments processes all media rows."""
    from arvel.facades import Storage
    from arvel_image import MediaLibrary

    await _create_tables_050(engine)
    Host = _host_050()
    host1 = await Host.create(name="alice")
    host2 = await Host.create(name="bob")

    with Storage.fake():
        await host1.add_media(jpeg_bytes, file_name="a.jpg").to_media_collection("gallery")
        await host2.add_media(jpeg_bytes, file_name="b.jpg").to_media_collection("gallery")

        lib = MediaLibrary()
        count = await lib.regenerate()  # no host, no collection

    assert count == 2


async def test_regenerate_no_args_returns_zero_for_empty_table(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """FR-050-01: regenerate() with no rows returns 0, not an error."""
    from arvel_image import MediaLibrary

    await _create_tables_050(engine)

    lib = MediaLibrary()
    count = await lib.regenerate()
    assert count == 0


async def test_regenerate_reads_from_media_disk_not_collection_disk(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-02: regenerate() reads from media.disk, not collection default disk."""
    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel.facades import Storage
    from arvel_image import Conversion, HasMedia, MediaCollection, MediaLibrary

    class HostConv050(Model, HasMedia, Timestamps):
        __tablename__ = "media_050_conv_hosts"
        id: Mapped[int] = id_()
        name: Mapped[str] = string(120)

        def register_media_collections(self) -> None:
            MediaCollection("photos").with_conversions(
                Conversion("thumb").fit("cover", 4, 4).format("png"),
            ).register_on(self)

    async with engine.begin() as conn:
        from arvel.database import Model

        await conn.run_sync(Model.metadata.create_all)

    host = await HostConv050.create(name="test")

    with Storage.fake():
        # Ingest onto "s3" disk explicitly
        media = await (
            host.add_media(jpeg_bytes, file_name="photo.jpg")
            .to_disk("s3")
            .to_media_collection("photos")
        )

    assert media.disk == "s3"

    # Now regenerate — it must read from "s3" (media.disk), not collection default
    read_calls: list[str] = []

    async def track_get(path: str) -> bytes:
        read_calls.append("s3")
        return jpeg_bytes

    with Storage.fake() as fake_storage2:
        fake_storage2.disk("s3").get = track_get  # type: ignore[method-assign]

        lib = MediaLibrary()
        await lib.regenerate()

    assert "s3" in read_calls, "regenerate() did not read from media.disk='s3'"


async def test_regenerate_writes_to_conversions_disk(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-03: regenerate() writes conversions to media.conversions_disk."""
    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel.facades import Storage
    from arvel_image import Conversion, HasMedia, MediaCollection, MediaLibrary

    class HostCDisk050(Model, HasMedia, Timestamps):
        __tablename__ = "media_050_cdisk_hosts"
        id: Mapped[int] = id_()
        name: Mapped[str] = string(120)

        def register_media_collections(self) -> None:
            MediaCollection("art").with_conversions(
                Conversion("thumb").fit("cover", 4, 4).format("png"),
            ).use_conversions_disk("thumbs").register_on(self)

    async with engine.begin() as conn:
        from arvel.database import Model

        await conn.run_sync(Model.metadata.create_all)

    host = await HostCDisk050.create(name="artist")

    with Storage.fake():
        media = await host.add_media(jpeg_bytes, file_name="art.jpg").to_media_collection("art")
        assert media.conversions_disk == "thumbs"

        lib = MediaLibrary()
        await lib.regenerate()


# ─── FR-050-04/05: order_column auto-assignment ───────────────────────────────


async def test_order_column_set_on_first_insert(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-04: first media in a collection gets order_column=1."""
    from arvel.facades import Storage

    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    with Storage.fake():
        media = await host.add_media(jpeg_bytes, file_name="a.jpg").to_media_collection("gallery")

    assert media.order_column == 1


async def test_order_column_increments_on_subsequent_inserts(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-04: second and third media get order_column=2 and 3."""
    from arvel.facades import Storage

    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    with Storage.fake():
        m1 = await host.add_media(jpeg_bytes, file_name="a.jpg").to_media_collection("gallery")
        m2 = await host.add_media(jpeg_bytes, file_name="b.jpg").to_media_collection("gallery")
        m3 = await host.add_media(jpeg_bytes, file_name="c.jpg").to_media_collection("gallery")

    assert m1.order_column == 1
    assert m2.order_column == 2
    assert m3.order_column == 3


async def test_order_column_resets_for_single_file_collection(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-05: single_file collection resets order_column to 1 on replace."""
    from arvel.facades import Storage

    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    with Storage.fake():
        await host.add_media(jpeg_bytes, file_name="old.jpg").to_media_collection("avatar")
        new_media = await host.add_media(jpeg_bytes, file_name="new.jpg").to_media_collection(
            "avatar"
        )

    assert new_media.order_column == 1


# ─── FR-050-06: Media.set_new_order ──────────────────────────────────────────


async def test_set_new_order_reorders_rows(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-06: set_new_order([id3, id1, id2]) assigns order_column=1,2,3."""
    from arvel.facades import Storage
    from arvel_image import Media

    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    with Storage.fake():
        m1 = await host.add_media(jpeg_bytes, file_name="a.jpg").to_media_collection("gallery")
        m2 = await host.add_media(jpeg_bytes, file_name="b.jpg").to_media_collection("gallery")
        m3 = await host.add_media(jpeg_bytes, file_name="c.jpg").to_media_collection("gallery")

    await Media.set_new_order([m3.id, m1.id, m2.id])

    await session.refresh(m1)
    await session.refresh(m2)
    await session.refresh(m3)

    assert m3.order_column == 1
    assert m1.order_column == 2
    assert m2.order_column == 3


async def test_set_new_order_with_start_order(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-06: start_order=5 makes first ID get order_column=5."""
    from arvel.facades import Storage
    from arvel_image import Media

    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    with Storage.fake():
        m1 = await host.add_media(jpeg_bytes, file_name="a.jpg").to_media_collection("gallery")
        m2 = await host.add_media(jpeg_bytes, file_name="b.jpg").to_media_collection("gallery")

    await Media.set_new_order([m1.id, m2.id], start_order=5)

    await session.refresh(m1)
    await session.refresh(m2)

    assert m1.order_column == 5
    assert m2.order_column == 6


async def test_set_new_order_skips_unknown_ids(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-06: unknown IDs are silently skipped."""
    from arvel.facades import Storage
    from arvel_image import Media

    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    with Storage.fake():
        m1 = await host.add_media(jpeg_bytes, file_name="a.jpg").to_media_collection("gallery")

    # 999999 does not exist — should not raise
    await Media.set_new_order([m1.id, 999999])

    await session.refresh(m1)
    assert m1.order_column == 1


# ─── FR-050-07/08: copy/move use host_pk + carry conversions ──────────────────


async def test_copy_uses_host_pk(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-07: copy() sets model_id = target.host_pk()."""
    from arvel.facades import Storage

    await _create_tables_050(engine)
    _host_custom_pk_050()
    Host = _host_050()
    HostCustomPk = _host_custom_pk_050()

    async with engine.begin() as conn:
        from arvel.database import Model

        await conn.run_sync(Model.metadata.create_all)

    src = await Host.create(name="src")
    dst = await HostCustomPk.create(name="dst")

    with Storage.fake():
        media = await src.add_media(jpeg_bytes, file_name="a.jpg").to_media_collection("gallery")
        copied = await media.copy(dst, "gallery")

    assert copied.model_id == dst.host_pk()
    assert copied.model_id == f"custom-{dst.id}"


async def test_move_uses_host_pk(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-07: move() sets model_id = target.host_pk()."""
    from arvel.facades import Storage

    await _create_tables_050(engine)
    _host_custom_pk_050()
    Host = _host_050()
    HostCustomPk = _host_custom_pk_050()

    async with engine.begin() as conn:
        from arvel.database import Model

        await conn.run_sync(Model.metadata.create_all)

    src = await Host.create(name="src")
    dst = await HostCustomPk.create(name="dst")

    with Storage.fake():
        media = await src.add_media(jpeg_bytes, file_name="a.jpg").to_media_collection("gallery")
        moved = await media.move(dst, "gallery")

    assert moved.model_id == dst.host_pk()


async def test_copy_carries_generated_conversions(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-08: copy() carries generated_conversions JSON."""
    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel.facades import Storage
    from arvel_image import Conversion, HasMedia, MediaCollection

    class HostCopy050(Model, HasMedia, Timestamps):
        __tablename__ = "media_050_copy_hosts"
        id: Mapped[int] = id_()
        name: Mapped[str] = string(120)

        def register_media_collections(self) -> None:
            MediaCollection("photos").with_conversions(
                Conversion("thumb").fit("cover", 4, 4).format("png"),
            ).register_on(self)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    src = await HostCopy050.create(name="src")
    dst = await HostCopy050.create(name="dst")

    with Storage.fake():
        media = await src.add_media(jpeg_bytes, file_name="a.jpg").to_media_collection("photos")
        assert media.generated_conversions.get("thumb") is True

        copied = await media.copy(dst, "photos")

    assert copied.generated_conversions.get("thumb") is True
    assert copied.uuid != media.uuid  # new UUID assigned


async def test_move_does_not_copy_files(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-08: move() does not copy conversion files — DB row only."""
    from arvel.facades import Storage

    await _create_tables_050(engine)
    Host = _host_050()
    src = await Host.create(name="src")
    dst = await Host.create(name="dst")

    put_calls: list[str] = []

    with Storage.fake() as fake:
        original_put = fake.disk().put

        async def track_put(path: str, data: bytes) -> None:
            put_calls.append(path)
            await original_put(path, data)

        fake.disk().put = track_put  # type: ignore[assignment]

        media = await src.add_media(jpeg_bytes, file_name="a.jpg").to_media_collection("gallery")
        put_calls.clear()  # clear the add_media put

        await media.move(dst, "gallery")

    assert put_calls == [], "move() should not write any files"


# ─── FR-050-09: MediaLibrary exported from arvel_image ───────────────────────


def test_media_library_importable_from_arvel_image() -> None:
    """FR-050-09: from arvel_image import MediaLibrary works."""
    from arvel_image import MediaLibrary

    assert MediaLibrary is not None


def test_media_library_in_dunder_all() -> None:
    """FR-050-09: MediaLibrary in arvel_image.__all__."""
    import arvel_image

    assert "MediaLibrary" in arvel_image.__all__


# ─── FR-050-10: to_media_collection disk override ────────────────────────────


async def test_to_media_collection_disk_arg_overrides_collection_disk(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-10: to_media_collection(name, disk='s3') stores on 's3'."""
    from arvel.facades import Storage

    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    with Storage.fake():
        media = await host.add_media(jpeg_bytes, file_name="a.jpg").to_media_collection(
            "gallery", "s3"
        )

    assert media.disk == "s3"


async def test_to_media_collection_disk_arg_overrides_to_disk_chain(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-10: disk arg takes priority over .to_disk() chain."""
    from arvel.facades import Storage

    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    with Storage.fake():
        media = await (
            host.add_media(jpeg_bytes, file_name="a.jpg")
            .to_disk("azure")  # lower priority
            .to_media_collection("gallery", "s3")  # higher priority
        )

    assert media.disk == "s3"


# ─── FR-050-11: URL scheme allowlist ─────────────────────────────────────────


async def test_add_media_from_url_rejects_file_scheme() -> None:
    """FR-050-11: file:// URLs raise MediaError before network I/O."""
    from arvel_image import HasMedia
    from arvel_image.media.exceptions import MediaError

    class FakeHost(HasMedia):
        def host_pk(self) -> str:
            return "1"

    host = FakeHost()
    with pytest.raises(MediaError, match="scheme"):
        await host.add_media_from_url("file:///etc/passwd")


async def test_add_media_from_url_rejects_ftp_scheme() -> None:
    """FR-050-11: ftp:// URLs raise MediaError."""
    from arvel_image import HasMedia
    from arvel_image.media.exceptions import MediaError

    class FakeHost2(HasMedia):
        def host_pk(self) -> str:
            return "1"

    host = FakeHost2()
    with pytest.raises(MediaError, match="scheme"):
        await host.add_media_from_url("ftp://example.com/file.jpg")


async def test_fetch_url_rejects_file_scheme() -> None:
    """FR-050-11: url_fetcher.fetch_url raises MediaError for file:// scheme."""
    from arvel_image.media.exceptions import MediaError
    from arvel_image.media.url_fetcher import fetch_url

    with pytest.raises(MediaError, match="scheme"):
        await fetch_url("file:///etc/passwd", max_bytes=1024)


# ─── FR-050-12: get_last_media / get_last_media_url ──────────────────────────


async def test_get_last_media_returns_highest_order_column(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-12: get_last_media returns row with highest order_column."""
    from arvel.facades import Storage

    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    with Storage.fake():
        await host.add_media(jpeg_bytes, file_name="a.jpg").to_media_collection("gallery")
        await host.add_media(jpeg_bytes, file_name="b.jpg").to_media_collection("gallery")
        m3 = await host.add_media(jpeg_bytes, file_name="c.jpg").to_media_collection("gallery")

    last = await host.get_last_media("gallery")
    assert last is not None
    assert last.id == m3.id


async def test_get_last_media_returns_none_for_empty_collection(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """FR-050-12: get_last_media returns None when collection is empty."""
    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    last = await host.get_last_media("gallery")
    assert last is None


async def test_get_last_media_url_returns_url(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-12: get_last_media_url returns URL of the last media."""
    from arvel.facades import Storage

    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    with Storage.fake():
        await host.add_media(jpeg_bytes, file_name="a.jpg").to_media_collection("gallery")
        await host.add_media(jpeg_bytes, file_name="b.jpg").to_media_collection("gallery")

        url = await host.get_last_media_url("gallery")
        assert url is not None
        assert isinstance(url, str)


async def test_get_last_media_url_returns_none_for_empty_collection(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """FR-050-12: get_last_media_url returns None for empty collection."""
    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    url = await host.get_last_media_url("gallery")
    assert url is None


# ─── FR-050-13: clear_media_collection_except ────────────────────────────────


async def test_clear_media_collection_except_deletes_others(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-13: clear_media_collection_except keeps the supplied item(s)."""
    from arvel.facades import Storage

    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    with Storage.fake():
        m1 = await host.add_media(jpeg_bytes, file_name="a.jpg").to_media_collection("gallery")
        m2 = await host.add_media(jpeg_bytes, file_name="b.jpg").to_media_collection("gallery")
        m3 = await host.add_media(jpeg_bytes, file_name="c.jpg").to_media_collection("gallery")

    with Storage.fake():
        await host.clear_media_collection_except("gallery", m2)

    remaining = await host.get_media("gallery")
    remaining_ids = {m.id for m in remaining}
    assert m2.id in remaining_ids
    assert m1.id not in remaining_ids
    assert m3.id not in remaining_ids


async def test_clear_media_collection_except_accepts_list(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-13: kept_media may be a list of Media instances."""
    from arvel.facades import Storage

    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    with Storage.fake():
        m1 = await host.add_media(jpeg_bytes, file_name="a.jpg").to_media_collection("gallery")
        m2 = await host.add_media(jpeg_bytes, file_name="b.jpg").to_media_collection("gallery")
        m3 = await host.add_media(jpeg_bytes, file_name="c.jpg").to_media_collection("gallery")

    with Storage.fake():
        await host.clear_media_collection_except("gallery", [m1, m3])

    remaining = await host.get_media("gallery")
    remaining_ids = {m.id for m in remaining}
    assert m1.id in remaining_ids
    assert m3.id in remaining_ids
    assert m2.id not in remaining_ids


# ─── FR-050-14: get_registered_media_collections ─────────────────────────────


async def test_get_registered_media_collections_returns_list(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """FR-050-14: get_registered_media_collections returns declared collections."""
    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    collections = host.get_registered_media_collections()
    names = {c.name for c in collections}
    assert "avatar" in names
    assert "gallery" in names
    assert "docs" in names


async def test_get_registered_media_collections_empty_when_none(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """FR-050-14: returns [] when no collections registered."""
    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel_image import HasMedia

    class HostNoColls050(Model, HasMedia, Timestamps):
        __tablename__ = "media_050_no_colls_hosts"
        id: Mapped[int] = id_()
        name: Mapped[str] = string(120)

    async with engine.begin() as conn:
        from arvel.database import Model

        await conn.run_sync(Model.metadata.create_all)

    host = await HostNoColls050.create(name="alice")
    assert host.get_registered_media_collections() == []


# ─── FR-050-15: per-collection fallback URL ──────────────────────────────────


def test_media_collection_use_fallback_url_stores_base() -> None:
    """FR-050-15: use_fallback_url stores the base fallback URL."""
    from arvel_image import MediaCollection

    coll = MediaCollection("avatar").use_fallback_url("/default.jpg")
    assert coll.get_fallback_url() == "/default.jpg"


def test_media_collection_use_fallback_url_stores_per_conversion() -> None:
    """FR-050-15: use_fallback_url(url, 'thumb') stores per-conversion fallback."""
    from arvel_image import MediaCollection

    coll = MediaCollection("avatar").use_fallback_url("/thumb.jpg", "thumb")
    assert coll.get_fallback_url("thumb") == "/thumb.jpg"


async def test_get_media_url_uses_collection_fallback_when_empty(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """FR-050-15: empty collection → collection fallback URL returned."""
    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel_image import HasMedia, MediaCollection

    class HostFallback050(Model, HasMedia, Timestamps):
        __tablename__ = "media_050_fallback_hosts"
        id: Mapped[int] = id_()
        name: Mapped[str] = string(120)

        def register_media_collections(self) -> None:
            MediaCollection("avatar").use_fallback_url("/default.jpg").register_on(self)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    host = await HostFallback050.create(name="alice")

    url = await host.get_media_url("avatar")
    assert url == "/default.jpg"


async def test_get_media_url_callsite_fallback_takes_precedence(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """FR-050-15: call-site fallback= takes precedence over collection fallback."""
    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel_image import HasMedia, MediaCollection

    class HostFallback2050(Model, HasMedia, Timestamps):
        __tablename__ = "media_050_fallback2_hosts"
        id: Mapped[int] = id_()
        name: Mapped[str] = string(120)

        def register_media_collections(self) -> None:
            MediaCollection("avatar").use_fallback_url("/collection-default.jpg").register_on(self)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    host = await HostFallback2050.create(name="alice")

    url = await host.get_media_url("avatar", fallback="/callsite.jpg")
    assert url == "/callsite.jpg"


# ─── FR-050-16/17: custom property helpers on Media ──────────────────────────


def test_has_custom_property_true_when_key_exists() -> None:
    """FR-050-16: has_custom_property returns True when key present."""
    import types

    from arvel_image import Media

    m = types.SimpleNamespace(custom_properties={"color": "red"})
    assert Media.has_custom_property(m, "color") is True  # type: ignore[arg-type]


def test_has_custom_property_false_when_key_missing() -> None:
    """FR-050-16: has_custom_property returns False when key absent."""
    import types

    from arvel_image import Media

    m = types.SimpleNamespace(custom_properties={})
    assert Media.has_custom_property(m, "color") is False  # type: ignore[arg-type]


def test_get_custom_property_returns_value() -> None:
    """FR-050-16: get_custom_property returns the stored value."""
    import types

    from arvel_image import Media

    m = types.SimpleNamespace(custom_properties={"alt": "landscape"})
    assert Media.get_custom_property(m, "alt") == "landscape"  # type: ignore[arg-type]


def test_get_custom_property_returns_default_when_missing() -> None:
    """FR-050-16: get_custom_property returns default when key absent."""
    import types

    from arvel_image import Media

    m = types.SimpleNamespace(custom_properties={})
    assert Media.get_custom_property(m, "missing", "fallback") == "fallback"  # type: ignore[arg-type]
    assert Media.get_custom_property(m, "missing") is None  # type: ignore[arg-type]


def test_get_custom_property_dot_notation() -> None:
    """FR-050-16: get_custom_property supports 'group.sub_key' dot notation."""
    import types

    from arvel_image import Media

    m = types.SimpleNamespace(custom_properties={"group": {"sub_key": "nested"}})
    assert Media.get_custom_property(m, "group.sub_key") == "nested"  # type: ignore[arg-type]


def test_set_custom_property_adds_key() -> None:
    """FR-050-16: set_custom_property adds/updates key in memory (not persisted)."""
    import types

    from arvel_image import Media

    m = types.SimpleNamespace(custom_properties={})
    Media.set_custom_property(m, "color", "blue")  # type: ignore[arg-type]
    assert m.custom_properties["color"] == "blue"


def test_forget_custom_property_removes_key() -> None:
    """FR-050-16: forget_custom_property removes the key."""
    import types

    from arvel_image import Media

    m = types.SimpleNamespace(custom_properties={"color": "red", "alt": "photo"})
    Media.forget_custom_property(m, "color")  # type: ignore[arg-type]
    assert "color" not in m.custom_properties


async def test_get_media_with_dict_filter(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-17: get_media(collection, filters={'key': 'val'}) filters by custom property."""
    from arvel.facades import Storage

    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    with Storage.fake():
        m_red = await (
            host.add_media(jpeg_bytes, file_name="a.jpg")
            .with_custom_properties({"color": "red"})
            .to_media_collection("gallery")
        )
        await (
            host.add_media(jpeg_bytes, file_name="b.jpg")
            .with_custom_properties({"color": "blue"})
            .to_media_collection("gallery")
        )

    reds = await host.get_media("gallery", filters={"color": "red"})
    assert len(reds) == 1
    assert reds[0].id == m_red.id


async def test_get_media_with_callable_filter(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-17: get_media(collection, filters=callable) applies the callable."""
    from arvel.facades import Storage

    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    with Storage.fake():
        m_visible = await (
            host.add_media(jpeg_bytes, file_name="a.jpg")
            .with_custom_properties({"visible": True})
            .to_media_collection("gallery")
        )
        await (
            host.add_media(jpeg_bytes, file_name="b.jpg")
            .with_custom_properties({"visible": False})
            .to_media_collection("gallery")
        )

    def _is_visible(m: Media) -> bool:
        return bool(m.custom_properties.get("visible"))

    visible = await host.get_media("gallery", filters=_is_visible)
    assert len(visible) == 1
    assert visible[0].id == m_visible.id


# ─── FR-050-18/19/20: QoL helpers on Media ───────────────────────────────────


def test_has_generated_conversion_returns_true() -> None:
    """FR-050-18: has_generated_conversion returns True for truthy entry."""
    import types

    from arvel_image import Media

    m = types.SimpleNamespace(generated_conversions={"thumb": True})
    assert Media.has_generated_conversion(m, "thumb") is True  # type: ignore[arg-type]


def test_has_generated_conversion_returns_false() -> None:
    """FR-050-18: has_generated_conversion returns False for missing/falsy."""
    import types

    from arvel_image import Media

    m = types.SimpleNamespace(generated_conversions={})
    assert Media.has_generated_conversion(m, "thumb") is False  # type: ignore[arg-type]


def test_human_readable_size_formats_bytes() -> None:
    """FR-050-20: human_readable_size returns '800 B' for 800 bytes."""
    import types

    from arvel_image import Media

    m = types.SimpleNamespace(size=800)
    assert Media.human_readable_size.fget(m) == "800 B"  # type: ignore[attr-defined]


def test_human_readable_size_formats_kilobytes() -> None:
    """FR-050-20: human_readable_size returns '1.0 KB' for 1024 bytes."""
    import types

    from arvel_image import Media

    m = types.SimpleNamespace(size=1024)
    result = Media.human_readable_size.fget(m)  # type: ignore[attr-defined]
    assert "KB" in result


def test_human_readable_size_formats_megabytes() -> None:
    """FR-050-20: human_readable_size returns MB string for large files."""
    import types

    from arvel_image import Media

    m = types.SimpleNamespace(size=1024 * 1024 + 512 * 1024)  # 1.5 MB
    result = Media.human_readable_size.fget(m)  # type: ignore[attr-defined]
    assert "MB" in result


async def test_get_full_url_returns_string(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-19: get_full_url returns a string URL."""
    from arvel.facades import Storage

    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    with Storage.fake():
        media = await host.add_media(jpeg_bytes, file_name="a.jpg").to_media_collection("gallery")
        url = await media.get_full_url()

    assert isinstance(url, str)
    assert len(url) > 0


# ─── FR-050-21/22/23: ingestion entry points ──────────────────────────────────


async def test_using_file_name_overrides_file_name(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-21: using_file_name('custom.jpg') stores file as custom.jpg."""
    from arvel.facades import Storage

    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    with Storage.fake():
        media = await (
            host.add_media(jpeg_bytes, file_name="original.jpg")
            .using_file_name("custom.jpg")
            .to_media_collection("gallery")
        )

    assert media.file_name == "custom.jpg"


async def test_set_file_name_is_alias_for_using_file_name(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-21: set_file_name is an alias for using_file_name."""
    from arvel.facades import Storage

    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    with Storage.fake():
        media = await (
            host.add_media(jpeg_bytes, file_name="original.jpg")
            .set_file_name("renamed.jpg")
            .to_media_collection("gallery")
        )

    assert media.file_name == "renamed.jpg"


async def test_add_media_from_disk_reads_and_creates_media(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes, tmp_path: Any
) -> None:
    """FR-050-22: add_media_from_disk reads file via Storage facade."""
    from arvel.facades import Storage

    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    disk_path = "uploads/photo.jpg"

    with Storage.fake() as fake:
        await fake.disk().put(disk_path, jpeg_bytes)

        fa = await host.add_media_from_disk(disk_path, disk="default")
        media = await fa.to_media_collection("gallery")

    assert media.file_name == "photo.jpg"
    assert media.size == len(jpeg_bytes)


async def test_add_media_from_string_creates_text_media(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """FR-050-23: add_media_from_string wraps content in BytesIO with default file_name."""
    from arvel.facades import Storage

    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    with Storage.fake():
        fa = host.add_media_from_string("hello world")
        media = await fa.to_media_collection("docs")

    assert media.file_name == "text.txt"
    assert media.size == len(b"hello world")


async def test_add_media_from_string_custom_file_name(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """FR-050-23: add_media_from_string supports using_file_name override."""
    from arvel.facades import Storage

    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    with Storage.fake():
        fa = host.add_media_from_string("content").using_file_name("readme.txt")
        media = await fa.to_media_collection("docs")

    assert media.file_name == "readme.txt"


# ─── FR-050-24/25: custom callbacks ──────────────────────────────────────────


async def test_sanitizing_file_name_callback_applied(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-24: sanitizing_file_name callback applied after built-in strip."""
    from arvel.facades import Storage

    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    def _sanitize(n: str) -> str:
        return n.lower().replace(" ", "-")

    with Storage.fake():
        media = await (
            host.add_media(jpeg_bytes, file_name="My Photo.jpg")
            .sanitizing_file_name(_sanitize)
            .to_media_collection("gallery")
        )

    assert media.file_name == "my-photo.jpg"


async def test_accepts_file_callback_rejects_wrong_mime(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes, png_bytes: bytes
) -> None:
    """FR-050-25: accepts_file callback raises InvalidMimeTypeError for non-matching files."""
    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel.facades import Storage
    from arvel_image import HasMedia, MediaCollection
    from arvel_image.media.exceptions import InvalidMimeTypeError

    class HostAccepts050(Model, HasMedia, Timestamps):
        __tablename__ = "media_050_accepts_hosts"
        id: Mapped[int] = id_()
        name: Mapped[str] = string(120)

        def register_media_collections(self) -> None:
            (
                MediaCollection("jpeg_only")
                .accepts_file(lambda f: f.mime_type == "image/jpeg")
                .register_on(self)
            )

    async with engine.begin() as conn:
        from arvel.database import Model

        await conn.run_sync(Model.metadata.create_all)

    host = await HostAccepts050.create(name="alice")

    with Storage.fake():
        # PNG should be rejected
        with pytest.raises(InvalidMimeTypeError):
            await host.add_media(png_bytes, file_name="photo.png").to_media_collection("jpeg_only")

        # JPEG should pass
        media = await host.add_media(jpeg_bytes, file_name="photo.jpg").to_media_collection(
            "jpeg_only"
        )
    assert media is not None


# ─── FR-050-26: delete_preserving_media ──────────────────────────────────────


async def test_delete_preserving_media_leaves_media_rows(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-26: delete_preserving_media deletes host but keeps Media rows."""
    from arvel.facades import Storage
    from arvel_image import Media

    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")
    host_id = host.id

    with Storage.fake():
        media = await host.add_media(jpeg_bytes, file_name="a.jpg").to_media_collection("gallery")
    media_id = media.id

    with Storage.fake():
        await host.delete_preserving_media()

    # Host row should be gone
    from arvel.database.session import get_active_session
    from sqlalchemy import select

    sess = get_active_session()
    HostCls = _host_050()
    result = await sess.execute(select(HostCls).where(HostCls.id == host_id))
    assert result.scalar_one_or_none() is None

    # Media row should still exist
    result2 = await sess.execute(select(Media).where(Media.id == media_id))
    surviving = result2.scalar_one_or_none()
    assert surviving is not None


# ─── FR-050-27: get_media("*") ───────────────────────────────────────────────


async def test_get_media_star_returns_all_collections(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-27: get_media('*') returns rows from all collections."""
    from arvel.facades import Storage

    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    with Storage.fake():
        await host.add_media(jpeg_bytes, file_name="a.jpg").to_media_collection("gallery")
        await host.add_media(jpeg_bytes, file_name="b.jpg").to_media_collection("docs")

    all_media = await host.get_media("*")
    assert len(all_media) == 2


async def test_get_media_no_args_returns_only_default(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FR-050-27: get_media() with no args still queries 'default' collection."""
    from arvel.facades import Storage

    await _create_tables_050(engine)
    Host = _host_050()
    host = await Host.create(name="alice")

    with Storage.fake():
        await host.add_media(jpeg_bytes, file_name="a.jpg").to_media_collection("gallery")
        await host.add_media(jpeg_bytes, file_name="b.jpg").to_media_collection("docs")

    # Should only return "default" collection (empty)
    default_media = await host.get_media()
    assert default_media == []


# ─── FR-050-28/29: PathGenerator DI + public rename ──────────────────────────


def test_get_media_ordered_is_public(engine: AsyncEngine) -> None:
    """FR-050-29: get_media_ordered is importable as a public function (no underscore)."""
    from arvel_image.media.trait import get_media_ordered

    assert get_media_ordered is not None


def test_private_get_media_ordered_does_not_exist() -> None:
    """FR-050-29: _get_media_ordered should no longer exist in trait module."""
    import arvel_image.media.trait as trait_mod

    assert not hasattr(trait_mod, "_get_media_ordered"), (
        "_get_media_ordered still exists; it should be renamed to get_media_ordered"
    )


def test_path_generator_di_resolution_uses_default_when_no_binding() -> None:
    """FR-050-28: resolve_path_generator() returns DefaultPathGenerator when no binding."""
    from arvel_image.media import file_adder
    from arvel_image.media.path_generator import DefaultPathGenerator

    gen = file_adder.resolve_path_generator()
    assert isinstance(gen, DefaultPathGenerator)
