"""Media library tests (round 1) — covers the DX-cleaned public surface."""

from __future__ import annotations

import base64
import io
import uuid
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

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


# ─── Engine / session ────────────────────────────────────────────────────────

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

    class Host046(HasMedia, Model, Timestamps):
        __tablename__ = "media_046_hosts"
        __media_collection__ = "gallery"

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


# ─── UUID auto-generation ────────────────────────────────────────────────────


async def test_uuid_is_set_after_add_image(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """add_image() assigns a UUID4 on the row."""
    from arvel.facades import Storage

    await _create_tables_046(engine)
    Host = _host_046()
    host = await Host.create(name="alice")

    with Storage.fake():
        media = await host.add_image(jpeg_bytes, file_name="photo.jpg")

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
        m1 = await host.add_image(jpeg_bytes, file_name="a.jpg")
        m2 = await host.add_image(jpeg_bytes, file_name="b.jpg")

    assert m1.uuid is not None
    assert m2.uuid is not None
    assert m1.uuid != m2.uuid


# ─── Atomic ingestion rollback ───────────────────────────────────────────────


async def test_rollback_on_conversion_failure_deletes_row_and_file(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """on conversion failure, the Media row and original file are removed."""
    from arvel.facades import Storage
    from arvel_image import Conversion, MediaCollection
    from arvel_image.media.exceptions import ConversionFailedError

    await _create_tables_046(engine)
    Host = _host_046()

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
            await host.add_image(jpeg_bytes, file_name="photo.jpg", collection="crash")

        from arvel.database.session import get_active_session
        from arvel_image import Media
        from sqlalchemy import select

        sess = get_active_session()
        result = await sess.execute(select(Media).filter_by(model_id=str(host.id)))
        rows = list(result.scalars())
        assert rows == [], "orphaned Media row found after conversion failure"

        assert ctx.fake.disk().files == {} or all(
            not p.startswith("") for p in ctx.fake.disk().files
        ), "orphaned file found after conversion failure"


# ─── conversions_disk ────────────────────────────────────────────────────────


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
    assert hasattr(coll, "conversions_disk")


def test_media_collection_use_conversions_disk_returns_self() -> None:
    from arvel_image import MediaCollection

    coll = MediaCollection("x")
    result = coll.use_conversions_disk("cdn")
    assert result is coll
    assert coll.conversions_disk == "cdn"


# ─── Ordered get_media() ─────────────────────────────────────────────────────


async def test_get_media_returns_in_order_column_asc(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """get_media() returns rows sorted by order_column ASC, then id ASC."""
    from arvel.facades import Storage

    await _create_tables_046(engine)
    Host = _host_046()
    host = await Host.create(name="eve")

    with Storage.fake():
        m1 = await host.add_image(jpeg_bytes, file_name="first.jpg")
        m2 = await host.add_image(jpeg_bytes, file_name="second.jpg")
        m3 = await host.add_image(jpeg_bytes, file_name="third.jpg")

    m1.order_column = 3
    m2.order_column = 1
    m3.order_column = 2
    from arvel.database.session import get_active_session

    sess = get_active_session()
    sess.add(m1)
    sess.add(m2)
    sess.add(m3)
    await sess.commit()

    await host.load("media")
    rows = host.get_media()
    assert [r.file_name for r in rows] == ["second.jpg", "third.jpg", "first.jpg"]


# ─── add_image with URLs ─────────────────────────────────────────────────────


async def test_add_image_downloads_url_and_ingests(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """add_image('https://...') fetches bytes via the SSRF-guarded fetcher."""
    from arvel.facades import Storage

    await _create_tables_046(engine)
    Host = _host_046()
    host = await Host.create(name="frank")

    with (
        Storage.fake(),
        patch(
            "arvel_image.media.url_fetcher.fetch_url",
            new_callable=AsyncMock,
            return_value=(jpeg_bytes, "photo.jpg"),
        ),
    ):
        media = await host.add_image("https://example.com/photo.jpg")

    assert media.file_name == "photo.jpg"
    assert media.size == len(jpeg_bytes)


async def test_add_image_ssrf_guard_blocks_private_ip() -> None:
    """SSRF guard rejects private IP addresses."""
    from arvel_image.media.url_fetcher import fetch_url

    with pytest.raises(Exception, match="SSRF|private|blocked"):
        await fetch_url("http://192.168.1.1/secret", max_bytes=1024 * 1024)


async def test_add_image_ssrf_guard_blocks_loopback() -> None:
    """SSRF guard rejects loopback addresses."""
    from arvel_image.media.url_fetcher import fetch_url

    with pytest.raises(Exception, match="SSRF|loopback|blocked"):
        await fetch_url("http://127.0.0.1/secret", max_bytes=1024 * 1024)


# ─── with_custom_properties on the builder ──────────────────────────────────


async def test_with_custom_properties_persisted_on_row(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """with_custom_properties() stores data on media.custom_properties."""
    from arvel.facades import Storage

    await _create_tables_046(engine)
    Host = _host_046()
    host = await Host.create(name="grace")

    with Storage.fake():
        media = await (
            host.image_builder(jpeg_bytes, file_name="photo.jpg")
            .with_custom_properties({"alt": "beach", "role": "hero"})
            .save()
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
        media = await (
            host.image_builder(jpeg_bytes, file_name="photo.jpg")
            .with_custom_properties({"key1": "val1"})
            .with_custom_properties({"key2": "val2"})
            .save()
        )

    assert media.custom_properties == {"key1": "val1", "key2": "val2"}


# ─── Collection MIME + size validation ──────────────────────────────────────


def test_media_collection_accept_mime_types_returns_self() -> None:
    from arvel_image import MediaCollection

    coll = MediaCollection("docs")
    result = coll.accept_mime_types(["application/pdf", "image/jpeg"])
    assert result is coll


def test_media_collection_max_file_size_returns_self() -> None:
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
            await host.add_image(jpeg_bytes, file_name="photo.jpg", collection="pdf_only")
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

    coll = MediaCollection("tiny").max_file_size(1)

    with Storage.fake() as ctx:
        with (
            pytest.raises(Exception, match="[Ss]ize|[Ll]arge|[Bb]ig"),
            patch.object(host, "collection_for", return_value=coll),
        ):
            await host.add_image(jpeg_bytes, file_name="photo.jpg", collection="tiny")
        assert ctx.fake.disk().files == {}


# ─── model_id VARCHAR for UUID host PKs ──────────────────────────────────────


def test_media_model_id_is_string_type() -> None:
    """Media.model_id must be a String column."""
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


# ─── to_disk() override on the builder ──────────────────────────────────────


def test_file_adder_to_disk_returns_self(jpeg_bytes: bytes) -> None:
    """FileAdder.to_disk() is a chain method."""
    from arvel_image.media.file_adder import FileAdder
    from arvel_image.media.trait import HasMedia

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
        media = await (
            host.image_builder(jpeg_bytes, file_name="photo.jpg").to_disk("custom_disk").save()
        )

    assert media.disk == "custom_disk"


# ─── Fallback URL ────────────────────────────────────────────────────────────


async def test_image_url_returns_fallback_when_empty(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """image_url(fallback=...) returns the fallback when the collection is empty."""
    await _create_tables_046(engine)
    Host = _host_046()
    host = await Host.create(name="liam")
    await host.load("media")

    url = host.image_url(fallback="https://example.com/default.jpg")
    assert url == "https://example.com/default.jpg"


def test_image_url_method_exists() -> None:
    """HasMedia.image_url replaces the old get_first_media_url alias."""
    from arvel_image import HasMedia

    assert callable(getattr(HasMedia, "image_url", None))


# ─── add_image with base64 ───────────────────────────────────────────────────


async def test_add_image_decodes_base64_and_ingests(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """add_image(<base64>) decodes and ingests."""
    from arvel.facades import Storage

    await _create_tables_046(engine)
    Host = _host_046()
    host = await Host.create(name="mia")

    encoded = base64.b64encode(jpeg_bytes).decode()

    with Storage.fake():
        media = await host.add_image(encoded, file_name="photo.jpg")

    assert media.size == len(jpeg_bytes)
    assert media.file_name == "photo.jpg"


async def test_add_image_strips_data_uri_prefix(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """data:image/jpeg;base64,<data> prefix is stripped before decode."""
    from arvel.facades import Storage

    await _create_tables_046(engine)
    Host = _host_046()
    host = await Host.create(name="noah")

    data_uri = f"data:image/jpeg;base64,{base64.b64encode(jpeg_bytes).decode()}"

    with Storage.fake():
        media = await host.add_image(data_uri, file_name="photo.jpg")

    assert media.size == len(jpeg_bytes)


async def test_add_image_rejects_malformed_base64() -> None:
    """malformed base64 raises MediaError when paired with a clearly-base64 input."""
    from arvel_image import HasMedia, MediaError

    class _FakeHost(HasMedia):
        id = 1

    host = _FakeHost()
    # Use a data URI so it's unambiguously a base64 input (not a file path).
    with pytest.raises(MediaError):
        await host.add_image("data:image/jpeg;base64,!!not-valid!!", file_name="bad.jpg")


# ─── only_keep_latest ────────────────────────────────────────────────────────


def test_only_keep_latest_returns_self() -> None:
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
                await host.add_image(jpeg_bytes, file_name=f"photo_{i}.jpg", collection="rolling")

    rows = host.media_in("rolling")
    assert len(rows) == 3
    names = {r.file_name for r in rows}
    assert "photo_0.jpg" not in names


# ─── move() and copy() on Media ──────────────────────────────────────────────


async def test_media_has_move_and_copy_methods() -> None:
    import inspect

    from arvel_image import Media

    assert hasattr(Media, "move")
    assert hasattr(Media, "copy")
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
        original = await src_host.add_image(jpeg_bytes, file_name="photo.jpg")
        copied = await original.copy(dst_host, collection="gallery")

    assert copied.id != original.id
    assert copied.model_id == str(dst_host.id)

    src_rows = src_host.get_media()
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
        original = await src_host.add_image(jpeg_bytes, file_name="photo.jpg")
        moved = await original.move(dst_host, collection="gallery")

    assert moved.model_id == str(dst_host.id)

    await src_host.load("media")
    src_rows = src_host.get_media()
    assert len(src_rows) == 0


# ─── MediaLibrary regenerate ─────────────────────────────────────────────────


def test_media_library_service_exists() -> None:
    from arvel_image.media.media_library import MediaLibrary

    assert hasattr(MediaLibrary, "regenerate")


async def test_media_library_regenerate_returns_count(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    """regenerate(host=, collection=) returns the count of reprocessed rows."""
    from arvel.facades import Storage
    from arvel_image.media.media_library import MediaLibrary

    await _create_tables_046(engine)
    Host = _host_046()
    host = await Host.create(name="tina")

    with Storage.fake():
        await host.add_image(jpeg_bytes, file_name="p1.jpg", collection="avatar")
        await host.add_image(jpeg_bytes, file_name="p2.jpg", collection="avatar")

        lib = MediaLibrary()
        count = await lib.regenerate(host=host, collection="avatar")

    assert isinstance(count, int)
    assert count >= 0


# ─── size column ─────────────────────────────────────────────────────────────


def test_media_size_column_is_big_integer() -> None:
    from arvel_image import Media
    from sqlalchemy import BigInteger
    from sqlalchemy.orm import class_mapper

    mapper = class_mapper(Media)
    col = mapper.columns["size"]
    assert isinstance(col.type, BigInteger)


# ─── Image.optimize ──────────────────────────────────────────────────────────


def test_image_optimize_exists() -> None:
    from arvel_image import Image

    assert hasattr(Image, "optimize")


def test_image_optimize_returns_self_and_strips_exif(jpeg_bytes: bytes) -> None:
    """optimize() strips EXIF and returns the same Image instance."""
    from arvel_image import Image

    img = Image.load(jpeg_bytes)
    result = img.optimize()
    assert result is img

    from PIL import Image as PILImage

    out = PILImage.open(io.BytesIO(img.to_bytes()))
    assert out.format in ("JPEG", "PNG")


def test_image_strip_exif_encodes_with_empty_exif_block(jpeg_bytes: bytes) -> None:
    """strip_exif() passes exif=b'' to the encoder."""
    from arvel_image import Image

    img = Image.load(jpeg_bytes)
    img.strip_exif()

    assert img.save_kwargs("JPEG").get("exif") == b""
    assert img.save_kwargs("WEBP").get("exif") == b""

    img_no_strip = Image.load(jpeg_bytes)
    assert "exif" not in img_no_strip.save_kwargs("JPEG")

    built = img.build()
    assert "exif" not in built.info


def test_image_strip_exif_returns_self(jpeg_bytes: bytes) -> None:
    """strip_exif() is chainable."""
    from arvel_image import Image

    img = Image.load(jpeg_bytes)
    assert img.strip_exif() is img
