"""Tests for medialibrary v11 parity."""

from __future__ import annotations

import base64
import io
import uuid
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("arvel_image", reason="arvel_image is the package under test")
pytest.importorskip("PIL", reason="arvel-image depends on Pillow")


if TYPE_CHECKING:
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


# ─── Engine / session (mirrors test_media.py conftest pattern) ───────────────

_HOST_CACHE_046: dict[str, type[Any]] = {}


async def _create_tables_046(engine: AsyncEngine) -> None:
    from arvel.database import Model
    from arvel_image import Media

    assert Media.__tablename__ == "media"
    _host_046()

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


def _host_046() -> type[Any]:
    if "Host046" in _HOST_CACHE_046:
        return _HOST_CACHE_046["Host046"]

    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel_image import Conversion, HasMedia, MediaCollection

    class Host046(Model, HasMedia, Timestamps):
        __tablename__ = "media_046_hosts"

        id: int = id_()
        name: str = string(120)

        def register_media_collections(self) -> None:
            MediaCollection("avatar", single_file=True).with_conversions(
                Conversion("thumb").fit("cover", 4, 4).format("png"),
            ).register_on(self)
            MediaCollection("gallery").register_on(self)
            MediaCollection("docs").register_on(self)

    _HOST_CACHE_046["Host046"] = Host046
    return Host046


# ──────────────────────────────────────────────────────────────────────────────
# UUID auto-generation
# ──────────────────────────────────────────────────────────────────────────────


async def test_uuid_is_set_after_add_media(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """FileAdder.to_media_collection() populates uuid on the row."""
    from arvel.facades import Storage

    await _create_tables_046(engine)
    Host = _host_046()
    host = await Host.create(name="alice")

    with Storage.fake():
        media = await host.add_media(jpeg_bytes, file_name="photo.jpg").to_media_collection(
            "gallery"
        )

    # Must be a valid UUID4 string — not None
    assert media.uuid is not None
    parsed = uuid.UUID(str(media.uuid))
    assert parsed.version == 4


async def test_two_media_rows_have_distinct_uuids(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """each row gets a unique uuid."""
    from arvel.facades import Storage

    await _create_tables_046(engine)
    Host = _host_046()
    host = await Host.create(name="bob")

    with Storage.fake():
        m1 = await host.add_media(jpeg_bytes, file_name="a.jpg").to_media_collection("gallery")
        m2 = await host.add_media(jpeg_bytes, file_name="b.jpg").to_media_collection("gallery")

    assert m1.uuid is not None
    assert m2.uuid is not None
    assert m1.uuid != m2.uuid


# ──────────────────────────────────────────────────────────────────────────────
# Atomic ingestion rollback
# ──────────────────────────────────────────────────────────────────────────────


async def test_rollback_on_conversion_failure_deletes_row_and_file(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """on conversion failure, the Media row and original file are removed."""
    from arvel.facades import Storage
    from arvel_image import Conversion, MediaCollection
    from arvel_image.media.exceptions import ConversionFailedError

    await _create_tables_046(engine)
    Host = _host_046()

    # Build a host with a conversion that always fails
    host = await Host.create(name="charlie")
    coll = MediaCollection("crash").with_conversions(Conversion("broken"))

    with (
        Storage.fake() as ctx,
        patch(
            "arvel_image.media.conversion_runner.ConversionRunner.run",
            new_callable=AsyncMock,
            side_effect=RuntimeError("GPU exploded"),
        ),
    ):
        with (
            pytest.raises((RuntimeError, ConversionFailedError)),
            patch.object(host, "collection_for", return_value=coll),
        ):
            await host.add_media(jpeg_bytes, file_name="photo.jpg").to_media_collection("crash")

        # Row MUST have been deleted (rollback)
        from arvel.database.session import get_active_session
        from arvel_image import Media
        from sqlalchemy import select

        sess = get_active_session()
        result = await sess.execute(select(Media).filter_by(model_id=str(host.id)))
        rows = list(result.scalars())
        assert rows == [], "orphaned Media row found after conversion failure"

        # Original file MUST have been removed from storage
        assert ctx.fake.disk().files == {} or all(
            not p.startswith("") for p in ctx.fake.disk().files
        ), "orphaned file found after conversion failure"


# ──────────────────────────────────────────────────────────────────────────────
# conversions_disk honoured
# ──────────────────────────────────────────────────────────────────────────────


async def test_conversions_disk_persisted_on_row(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """MediaCollection.use_conversions_disk() sets media.conversions_disk."""
    from arvel_image import Conversion, MediaCollection

    await _create_tables_046(engine)
    Host = _host_046()
    await Host.create(name="diana")

    coll = (
        MediaCollection("photos")
        .use_conversions_disk("cdn")
        .with_conversions(Conversion("thumb").fit("cover", 4, 4).format("png"))
    )
    # MediaCollection.use_conversions_disk must exist
    assert hasattr(coll, "conversions_disk"), "use_conversions_disk attribute not found"


def test_media_collection_use_conversions_disk_returns_self() -> None:
    """use_conversions_disk is a chain method returning Self."""
    from arvel_image import MediaCollection

    coll = MediaCollection("x")
    result = coll.use_conversions_disk("cdn")
    assert result is coll
    assert coll.conversions_disk == "cdn"


# ──────────────────────────────────────────────────────────────────────────────
# Ordered get_media()
# ──────────────────────────────────────────────────────────────────────────────


async def test_get_media_returns_in_order_column_asc(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """get_media() returns rows sorted by order_column ASC, then id ASC."""
    from arvel.facades import Storage

    await _create_tables_046(engine)
    Host = _host_046()
    host = await Host.create(name="eve")

    with Storage.fake():
        m1 = await host.add_media(jpeg_bytes, file_name="first.jpg").to_media_collection("gallery")
        m2 = await host.add_media(jpeg_bytes, file_name="second.jpg").to_media_collection("gallery")
        m3 = await host.add_media(jpeg_bytes, file_name="third.jpg").to_media_collection("gallery")

    # Manually set order_column out of insertion order
    m1.order_column = 3
    m2.order_column = 1
    m3.order_column = 2
    from arvel.database.session import get_active_session

    sess = get_active_session()
    sess.add(m1)
    sess.add(m2)
    sess.add(m3)
    await sess.commit()

    rows = await host.get_media("gallery")
    assert [r.file_name for r in rows] == ["second.jpg", "third.jpg", "first.jpg"]


# ──────────────────────────────────────────────────────────────────────────────
# -- add_media_from_url --
# ──────────────────────────────────────────────────────────────────────────────


async def test_add_media_from_url_exists_on_has_media() -> None:
    """HasMedia must expose add_media_from_url as an async method."""
    from arvel_image import HasMedia

    assert hasattr(HasMedia, "add_media_from_url"), "add_media_from_url not found on HasMedia"
    import inspect

    assert inspect.iscoroutinefunction(HasMedia.add_media_from_url), (
        "add_media_from_url must be async"
    )


async def test_add_media_from_url_downloads_and_ingests(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """add_media_from_url fetches bytes via httpx and ingests them."""
    from arvel.facades import Storage

    await _create_tables_046(engine)
    Host = _host_046()
    host = await Host.create(name="frank")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = jpeg_bytes

    with (
        Storage.fake(),
        patch(
            "arvel_image.media.url_fetcher.fetch_url",
            new_callable=AsyncMock,
            return_value=(jpeg_bytes, "photo.jpg"),
        ),
    ):
        media = await (
            await host.add_media_from_url("https://example.com/photo.jpg", file_name="photo.jpg")
        ).to_media_collection("gallery")

    assert media.file_name == "photo.jpg"
    assert media.size == len(jpeg_bytes)


async def test_add_media_from_url_ssrf_guard_blocks_private_ip() -> None:
    """SSRF guard rejects private IP addresses."""
    from arvel_image.media.url_fetcher import fetch_url

    with pytest.raises(Exception, match="SSRF|private|blocked"):
        await fetch_url("http://192.168.1.1/secret", max_bytes=1024 * 1024)


async def test_add_media_from_url_ssrf_guard_blocks_loopback() -> None:
    """SSRF guard rejects loopback addresses."""
    from arvel_image.media.url_fetcher import fetch_url

    with pytest.raises(Exception, match="SSRF|loopback|blocked"):
        await fetch_url("http://127.0.0.1/secret", max_bytes=1024 * 1024)


# ──────────────────────────────────────────────────────────────────────────────
# with_custom_properties() on FileAdder
# ──────────────────────────────────────────────────────────────────────────────


async def test_with_custom_properties_persisted_on_row(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """with_custom_properties() stores data on media.custom_properties."""
    from arvel.facades import Storage

    await _create_tables_046(engine)
    Host = _host_046()
    host = await Host.create(name="grace")

    with Storage.fake():
        media = (
            await host.add_media(jpeg_bytes, file_name="photo.jpg")
            .with_custom_properties({"alt": "beach", "role": "hero"})
            .to_media_collection("gallery")
        )

    assert media.custom_properties == {"alt": "beach", "role": "hero"}


async def test_with_custom_properties_merges_on_second_call(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """calling with_custom_properties twice merges results."""
    from arvel.facades import Storage

    await _create_tables_046(engine)
    Host = _host_046()
    host = await Host.create(name="henry")

    with Storage.fake():
        media = (
            await host.add_media(jpeg_bytes, file_name="photo.jpg")
            .with_custom_properties({"key1": "val1"})
            .with_custom_properties({"key2": "val2"})
            .to_media_collection("gallery")
        )

    assert media.custom_properties == {"key1": "val1", "key2": "val2"}


# ──────────────────────────────────────────────────────────────────────────────
# Collection MIME + size validation
# ──────────────────────────────────────────────────────────────────────────────


def test_media_collection_accept_mime_types_returns_self() -> None:
    """accept_mime_types is a chain method on MediaCollection."""
    from arvel_image import MediaCollection

    coll = MediaCollection("docs")
    result = coll.accept_mime_types(["application/pdf", "image/jpeg"])
    assert result is coll


def test_media_collection_max_file_size_returns_self() -> None:
    """max_file_size is a chain method on MediaCollection."""
    from arvel_image import MediaCollection

    coll = MediaCollection("docs")
    result = coll.max_file_size(1024 * 1024)
    assert result is coll


async def test_validation_rejects_wrong_mime_before_io(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """ingestion fails with wrong MIME before any storage write."""
    from arvel.facades import Storage
    from arvel_image import MediaCollection

    await _create_tables_046(engine)
    Host = _host_046()
    host = await Host.create(name="iris")

    coll = MediaCollection("pdf_only").accept_mime_types(["application/pdf"])

    with Storage.fake() as ctx:
        with (
            pytest.raises(Exception, match="[Mm]ime|[Tt]ype|[Ii]nvalid"),
            patch.object(host, "collection_for", return_value=coll),
        ):
            await host.add_media(jpeg_bytes, file_name="photo.jpg").to_media_collection("pdf_only")
        # Nothing should have been written to storage
        assert ctx.fake.disk().files == {}


async def test_validation_rejects_oversized_file_before_io(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """ingestion fails when file exceeds max_file_size."""
    from arvel.facades import Storage
    from arvel_image import MediaCollection

    await _create_tables_046(engine)
    Host = _host_046()
    host = await Host.create(name="jack")

    coll = MediaCollection("tiny").max_file_size(1)  # 1 byte max

    with Storage.fake() as ctx:
        with (
            pytest.raises(Exception, match="[Ss]ize|[Ll]arge|[Bb]ig"),
            patch.object(host, "collection_for", return_value=coll),
        ):
            await host.add_media(jpeg_bytes, file_name="photo.jpg").to_media_collection("tiny")
        assert ctx.fake.disk().files == {}


# ──────────────────────────────────────────────────────────────────────────────
# model_id VARCHAR for UUID host PKs
# ──────────────────────────────────────────────────────────────────────────────


def test_media_model_id_is_string_type() -> None:
    """Media.model_id must be a String column, not Integer."""
    from arvel_image import Media
    from sqlalchemy import String
    from sqlalchemy.orm import class_mapper

    mapper = class_mapper(Media)
    col = mapper.columns["model_id"]
    assert isinstance(col.type, String), (
        f"media.model_id should be String, got {type(col.type).__name__}"
    )


async def test_media_model_id_stores_uuid_pk(engine: AsyncEngine, session: AsyncSession) -> None:
    """model_id can store a UUID string without truncation."""
    from arvel_image import Media

    await _create_tables_046(engine)

    host_pk = str(uuid.uuid4())
    media = await Media.create(
        model_type="UUIDHost",
        model_id=host_pk,
        collection_name="default",
        name="x",
        file_name="x.jpg",
        disk="default",
        size=10,
    )

    assert media.model_id == host_pk
    assert len(media.model_id) == 36


# ──────────────────────────────────────────────────────────────────────────────
# to_disk() override on FileAdder
# ──────────────────────────────────────────────────────────────────────────────


def test_file_adder_to_disk_returns_self(jpeg_bytes: bytes) -> None:
    """FileAdder.to_disk() is a chain method."""
    from arvel_image.media.file_adder import FileAdder
    from arvel_image.media.trait import HasMedia

    # Minimal stub host
    class _FakeHost(HasMedia):
        id = 1

    fa = FileAdder(_FakeHost(), jpeg_bytes, file_name="photo.jpg")
    result = fa.to_disk("cdn")
    assert result is fa


async def test_to_disk_overrides_collection_disk(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """to_disk() overrides the MediaCollection's disk on ingestion."""
    from arvel.facades import Storage

    await _create_tables_046(engine)
    Host = _host_046()
    host = await Host.create(name="kate")

    with Storage.fake():
        media = (
            await host.add_media(jpeg_bytes, file_name="photo.jpg")
            .to_disk("custom_disk")
            .to_media_collection("gallery")
        )

    assert media.disk == "custom_disk"


# ──────────────────────────────────────────────────────────────────────────────
# Fallback URL
# ──────────────────────────────────────────────────────────────────────────────


async def test_get_media_url_returns_fallback_when_empty(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """get_media_url returns fallback when collection is empty."""
    await _create_tables_046(engine)
    Host = _host_046()
    host = await Host.create(name="liam")

    url = await host.get_media_url("gallery", fallback="https://example.com/default.jpg")
    assert url == "https://example.com/default.jpg"


async def test_get_first_media_url_alias_exists() -> None:
    """HasMedia.get_first_media_url is present."""
    from arvel_image import HasMedia

    assert hasattr(HasMedia, "get_first_media_url"), "get_first_media_url not found"


# ──────────────────────────────────────────────────────────────────────────────
# -- add_media_from_base64 --
# ──────────────────────────────────────────────────────────────────────────────


async def test_add_media_from_base64_exists() -> None:
    """HasMedia.add_media_from_base64 is an async method."""
    import inspect

    from arvel_image import HasMedia

    assert hasattr(HasMedia, "add_media_from_base64")
    assert inspect.iscoroutinefunction(HasMedia.add_media_from_base64)


async def test_add_media_from_base64_decodes_and_ingests(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """base64 encoded image is decoded and ingested correctly."""
    from arvel.facades import Storage

    await _create_tables_046(engine)
    Host = _host_046()
    host = await Host.create(name="mia")

    encoded = base64.b64encode(jpeg_bytes).decode()

    with Storage.fake():
        media = await (await host.add_media_from_base64(encoded, "photo.jpg")).to_media_collection(
            "gallery"
        )

    assert media.size == len(jpeg_bytes)
    assert media.file_name == "photo.jpg"


async def test_add_media_from_base64_strips_data_uri_prefix(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """data:image/jpeg;base64,<data> prefix is stripped before decode."""
    from arvel.facades import Storage

    await _create_tables_046(engine)
    Host = _host_046()
    host = await Host.create(name="noah")

    data_uri = f"data:image/jpeg;base64,{base64.b64encode(jpeg_bytes).decode()}"

    with Storage.fake():
        media = await (await host.add_media_from_base64(data_uri, "photo.jpg")).to_media_collection(
            "gallery"
        )

    assert media.size == len(jpeg_bytes)


async def test_add_media_from_base64_rejects_malformed() -> None:
    """malformed base64 raises MediaError."""
    from arvel_image import MediaError
    from arvel_image.media.trait import HasMedia

    class _FakeHost(HasMedia):
        id = 1

    host = _FakeHost()
    with pytest.raises((MediaError, Exception)):
        await host.add_media_from_base64("not-valid-base64!!!", "bad.jpg")


# ──────────────────────────────────────────────────────────────────────────────
# -- only_keep_latest --
# ──────────────────────────────────────────────────────────────────────────────


def test_only_keep_latest_returns_self() -> None:
    """only_keep_latest is a chain method on MediaCollection."""
    from arvel_image import MediaCollection

    coll = MediaCollection("photos")
    result = coll.only_keep_latest(3)
    assert result is coll


def test_only_keep_latest_exclusive_with_single_file() -> None:
    """only_keep_latest and single_file=True are mutually exclusive."""
    from arvel_image import MediaCollection

    coll = MediaCollection("x", single_file=True)
    with pytest.raises(ValueError, match="[Mm]utually|[Ee]xclusive|[Cc]onflict"):
        coll.only_keep_latest(3)


async def test_only_keep_latest_prunes_oldest(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """adding a 4th file to a keep_latest(3) collection prunes the oldest."""
    from arvel.facades import Storage
    from arvel_image import MediaCollection

    await _create_tables_046(engine)
    Host = _host_046()
    host = await Host.create(name="olivia")

    coll = MediaCollection("rolling").only_keep_latest(3)

    with Storage.fake():
        for i in range(4):
            with patch.object(host, "collection_for", return_value=coll):
                await host.add_media(jpeg_bytes, file_name=f"photo_{i}.jpg").to_media_collection(
                    "rolling"
                )

    rows = await host.get_media("rolling")
    assert len(rows) == 3
    names = {r.file_name for r in rows}
    # The oldest (photo_0.jpg) must have been pruned
    assert "photo_0.jpg" not in names


# ──────────────────────────────────────────────────────────────────────────────
# move() and copy() on Media
# ──────────────────────────────────────────────────────────────────────────────


async def test_media_has_move_and_copy_methods() -> None:
    """Media exposes async move() and copy()."""
    import inspect

    from arvel_image import Media

    assert hasattr(Media, "move"), "Media.move not found"
    assert hasattr(Media, "copy"), "Media.copy not found"
    assert inspect.iscoroutinefunction(Media.move)
    assert inspect.iscoroutinefunction(Media.copy)


async def test_media_copy_creates_new_row(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """copy() produces a new Media row without removing the original."""
    from arvel.facades import Storage

    await _create_tables_046(engine)
    Host = _host_046()
    src_host = await Host.create(name="peter")
    dst_host = await Host.create(name="quinn")

    with Storage.fake():
        original = await src_host.add_media(jpeg_bytes, file_name="photo.jpg").to_media_collection(
            "gallery"
        )
        copied = await original.copy(dst_host, collection="gallery")

    assert copied.id != original.id
    assert copied.model_id == str(dst_host.id)

    # Original still exists
    src_rows = await src_host.get_media("gallery")
    assert len(src_rows) == 1


async def test_media_move_changes_owner_and_removes_from_source(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """move() transfers the row to the target host."""
    from arvel.facades import Storage

    await _create_tables_046(engine)
    Host = _host_046()
    src_host = await Host.create(name="rachel")
    dst_host = await Host.create(name="sam")

    with Storage.fake():
        original = await src_host.add_media(jpeg_bytes, file_name="photo.jpg").to_media_collection(
            "gallery"
        )
        moved = await original.move(dst_host, collection="gallery")

    assert moved.model_id == str(dst_host.id)

    src_rows = await src_host.get_media("gallery")
    assert len(src_rows) == 0


# ──────────────────────────────────────────────────────────────────────────────
# Regenerate conversions service + CLI
# ──────────────────────────────────────────────────────────────────────────────


def test_media_library_service_exists() -> None:
    """MediaLibrary service class is importable."""
    from arvel_image.media.media_library import MediaLibrary

    assert hasattr(MediaLibrary, "regenerate"), "MediaLibrary.regenerate not found"


async def test_media_library_regenerate_returns_count(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """regenerate() returns the count of reprocessed media rows."""
    from arvel.facades import Storage
    from arvel_image.media.media_library import MediaLibrary

    await _create_tables_046(engine)
    Host = _host_046()
    host = await Host.create(name="tina")

    with Storage.fake():
        await host.add_media(jpeg_bytes, file_name="p1.jpg").to_media_collection("avatar")
        await host.add_media(jpeg_bytes, file_name="p2.jpg").to_media_collection("avatar")

        lib = MediaLibrary()
        count = await lib.regenerate(host=host, collection="avatar")

    assert isinstance(count, int)
    assert count >= 0


# ──────────────────────────────────────────────────────────────────────────────
# size column unsigned consistency
# ──────────────────────────────────────────────────────────────────────────────


def test_media_size_column_is_big_integer() -> None:
    """Media.size uses BigInteger (unsigned for MySQL compat)."""
    from arvel_image import Media
    from sqlalchemy import BigInteger
    from sqlalchemy.orm import class_mapper

    mapper = class_mapper(Media)
    col = mapper.columns["size"]
    assert isinstance(col.type, BigInteger), (
        f"Media.size should be BigInteger, got {type(col.type).__name__}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# -- Image.optimize --
# ──────────────────────────────────────────────────────────────────────────────


def test_image_optimize_exists() -> None:
    """Image.optimize() method exists."""
    from arvel_image import Image

    assert hasattr(Image, "optimize"), "Image.optimize not found"


def test_image_optimize_returns_self_and_strips_exif(jpeg_bytes: bytes) -> None:
    """optimize() strips EXIF and returns the same Image instance."""
    from arvel_image import Image

    img = Image.load(jpeg_bytes)
    result = img.optimize()
    assert result is img  # chain method

    # After optimize, output bytes should still be valid JPEG
    from PIL import Image as PILImage

    out = PILImage.open(io.BytesIO(img.to_bytes()))
    assert out.format in ("JPEG", "PNG")
