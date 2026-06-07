"""MediaLibrary.regenerate() integration test against MinIO.

Closes the unit-mock gap on the only path that touches a real S3 driver.
Unit tests use ``Storage.fake()`` (in-memory); this exercises the wire
protocol — multipart, content-type, S3v4 signatures, redirect handling.

Marked ``requires_emulator`` — opt-in via ``pytest -m requires_emulator``.
The default test selector excludes it (see ``addopts`` in pyproject.toml).
"""

from __future__ import annotations

import contextlib
import io
from typing import TYPE_CHECKING, Any, Protocol

import pytest

pytest.importorskip("arvel_image", reason="arvel_image is the package under test")
pytest.importorskip("PIL", reason="arvel-image depends on Pillow")
pytest.importorskip("aioboto3", reason="S3Driver requires aioboto3")
pytest.importorskip("boto3", reason="MinIO fixtures require boto3")
pytest.importorskip("testcontainers", reason="MinIO container needs testcontainers")

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


# Mirror of conftest.MinioEndpoint's shape — typed locally to avoid the
# relative-import gymnastics (no __init__.py in tests/, mypy collision with
# sibling packages). pytest injects the dataclass by fixture name; this
# Protocol is structurally compatible.
class _MinioEndpointLike(Protocol):
    endpoint_url: str
    region: str
    access_key: str
    secret_key: str
    bucket: str


pytestmark = [pytest.mark.requires_emulator, pytest.mark.integration]


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _jpeg(width: int = 500, height: int = 375) -> bytes:
    from PIL import Image as PILImage

    buf = io.BytesIO()
    PILImage.new("RGB", (width, height), (200, 100, 50)).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


_HOST_F: dict[str, type[Any]] = {}


def _host_f() -> type[Any]:
    if "HostF" in _HOST_F:
        return _HOST_F["HostF"]
    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel_image import Conversion, HasMedia, MediaCollection

    class HostF(HasMedia, Model, Timestamps):
        __tablename__ = "media_track_f_hosts"
        __media_collection__ = "gallery"
        id: int = id_()
        name: str = string(120)

        def register_media_collections(self) -> None:
            MediaCollection("gallery").with_conversions(
                Conversion("thumb").fit("cover", 64, 64).format("png"),
            ).register_on(self)

    _HOST_F["HostF"] = HostF
    return HostF


def _clear_collection_cache(host_cls: type[Any]) -> None:
    """Clear HasMedia's per-class collection cache so next call re-registers."""
    for attr in ("__arvel_collections_registered__", "__arvel_media_collections__"):
        with contextlib.suppress(AttributeError):
            delattr(host_cls, attr)


def _add_card_conversion_to_host_f() -> None:
    """Mutate HostF.register_media_collections to add a 'card' conversion.

    Simulates the "developer added a new conversion after media existed"
    workflow without creating a second SQLAlchemy class (same __tablename__
    on the same MetaData would raise InvalidRequestError). Clears the
    HasMedia registration cache so the next collection_for() call rebuilds.
    """
    from arvel_image import Conversion, MediaCollection

    Host = _host_f()

    def _register_with_card(self: Any) -> None:
        MediaCollection("gallery").with_conversions(
            Conversion("thumb").fit("cover", 64, 64).format("png"),
            Conversion("card").fit("contain", 200, 150).format("webp"),
        ).register_on(self)

    Host.register_media_collections = _register_with_card
    _clear_collection_cache(Host)


def _restore_host_f_registration() -> None:
    """Revert _add_card_conversion_to_host_f for other tests in the session."""
    from arvel_image import Conversion, MediaCollection

    Host = _host_f()

    def _register_original(self: Any) -> None:
        MediaCollection("gallery").with_conversions(
            Conversion("thumb").fit("cover", 64, 64).format("png"),
        ).register_on(self)

    Host.register_media_collections = _register_original
    _clear_collection_cache(Host)


async def _create_tables_track_f(engine: AsyncEngine) -> None:
    from arvel.database import Model
    from arvel_image import Media

    assert Media.__tablename__ == "media"
    _host_f()

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


def _make_s3_manager(endpoint: _MinioEndpointLike, bucket: str) -> Any:
    """Build a real StorageManager bound to MinIO."""
    from arvel.config.storage_config import S3Config, StorageConfig
    from arvel.storage import StorageManager
    from pydantic import SecretStr

    s3_config = S3Config(
        key=SecretStr(endpoint.access_key),
        secret=SecretStr(endpoint.secret_key),
        region=endpoint.region,
        bucket=bucket,
        endpoint=endpoint.endpoint_url,
        addressing_style="path",  # MinIO requires path-style addressing
        signature_version="s3v4",
    )
    storage_config = StorageConfig(default="s3")
    return StorageManager(config=storage_config, s3_config=s3_config)


# ─── basic round-trip ────────────────────────────────────────────────────────


async def test_regenerate_round_trips_through_minio(
    engine: AsyncEngine,
    session: AsyncSession,
    minio_endpoint: _MinioEndpointLike,
    minio_bucket: str,
) -> None:
    from arvel.facades.storage import Storage
    from arvel_image.media.media_library import MediaLibrary

    await _create_tables_track_f(engine)
    Host = _host_f()
    host = await Host.create(name="alice")

    manager = _make_s3_manager(minio_endpoint, minio_bucket)
    previous = Storage.swap_manager(manager)
    try:
        media = await host.add_image(_jpeg(), file_name="photo.jpg", collection="gallery")

        source_path = f"{media.id}/photo.jpg"
        conversion_path = f"{media.id}/conversions/thumb-photo.jpg"
        s3 = Storage.disk("s3")

        assert await s3.exists(source_path), "source must be uploaded to MinIO"
        assert await s3.exists(conversion_path), "thumb conversion must be uploaded on first add"

        original_thumb_bytes = await s3.get(conversion_path)
        assert original_thumb_bytes.startswith(b"\x89PNG"), "thumb must be a real PNG"

        lib = MediaLibrary()
        count = await lib.regenerate(host=host, collection="gallery")
        assert count == 1, "regenerate must process exactly one row"

        assert await s3.exists(conversion_path), "thumb must still exist after regenerate"
        regenerated_thumb_bytes = await s3.get(conversion_path)
        assert regenerated_thumb_bytes.startswith(b"\x89PNG")
        assert regenerated_thumb_bytes == original_thumb_bytes, (
            "regenerate against unchanged source must produce byte-equal output"
        )
    finally:
        Storage.swap_manager(previous)


# ─── regenerate fills in newly-added conversions ─────────────────────────────


async def test_regenerate_creates_newly_added_conversion(
    engine: AsyncEngine,
    session: AsyncSession,
    minio_endpoint: _MinioEndpointLike,
    minio_bucket: str,
) -> None:
    from arvel.facades.storage import Storage
    from arvel_image.media.media_library import MediaLibrary

    await _create_tables_track_f(engine)
    Host = _host_f()
    host = await Host.create(name="bob")

    manager = _make_s3_manager(minio_endpoint, minio_bucket)
    previous = Storage.swap_manager(manager)
    try:
        media = await host.add_image(_jpeg(), file_name="hero.jpg", collection="gallery")

        s3 = Storage.disk("s3")
        thumb_path = f"{media.id}/conversions/thumb-hero.jpg"
        card_path = f"{media.id}/conversions/card-hero.jpg"

        assert await s3.exists(thumb_path)
        assert not await s3.exists(card_path), (
            "card conversion shouldn't exist before re-registration"
        )

        _add_card_conversion_to_host_f()
        host_with_card = await Host.find(host.id)
        assert host_with_card is not None

        lib = MediaLibrary()
        count = await lib.regenerate(host=host_with_card, collection="gallery")
        assert count == 1

        assert await s3.exists(thumb_path), "existing thumb must remain"
        assert await s3.exists(card_path), "new card conversion must be generated by regenerate()"
        card_bytes = await s3.get(card_path)
        # WebP magic: RIFF....WEBP
        assert card_bytes[:4] == b"RIFF"
        assert card_bytes[8:12] == b"WEBP"
    finally:
        Storage.swap_manager(previous)
        _restore_host_f_registration()


# ─── idempotency under repeated regeneration ─────────────────────────────────


async def test_regenerate_is_idempotent(
    engine: AsyncEngine,
    session: AsyncSession,
    minio_endpoint: _MinioEndpointLike,
    minio_bucket: str,
) -> None:
    from arvel.facades.storage import Storage
    from arvel_image.media.media_library import MediaLibrary

    await _create_tables_track_f(engine)
    Host = _host_f()
    host = await Host.create(name="carol")

    manager = _make_s3_manager(minio_endpoint, minio_bucket)
    previous = Storage.swap_manager(manager)
    try:
        media = await host.add_image(_jpeg(), file_name="picture.jpg", collection="gallery")
        conversion_path = f"{media.id}/conversions/thumb-picture.jpg"
        s3 = Storage.disk("s3")

        first_bytes = await s3.get(conversion_path)

        lib = MediaLibrary()
        for _ in range(3):
            count = await lib.regenerate(host=host, collection="gallery")
            assert count == 1

        third_bytes = await s3.get(conversion_path)
        assert first_bytes == third_bytes, (
            "3x regenerate against unchanged source must produce byte-equal output"
        )
    finally:
        Storage.swap_manager(previous)


# ─── survives missing source bytes ───────────────────────────────────────────


async def test_regenerate_skips_when_source_is_missing(
    engine: AsyncEngine,
    session: AsyncSession,
    minio_endpoint: _MinioEndpointLike,
    minio_bucket: str,
) -> None:
    """Source file deleted externally (manual cleanup, S3 lifecycle policy).

    regenerate() must skip silently rather than throw — that's the contract
    documented in process_one() ("Source file is gone... silently skip").
    """
    from arvel.facades.storage import Storage
    from arvel_image.media.media_library import MediaLibrary

    await _create_tables_track_f(engine)
    Host = _host_f()
    host = await Host.create(name="dave")

    manager = _make_s3_manager(minio_endpoint, minio_bucket)
    previous = Storage.swap_manager(manager)
    try:
        media = await host.add_image(_jpeg(), file_name="ghost.jpg", collection="gallery")

        # Delete the source from MinIO directly — simulates lifecycle eviction
        s3 = Storage.disk("s3")
        source_path = f"{media.id}/ghost.jpg"
        assert await s3.exists(source_path)
        await s3.delete(source_path)
        assert not await s3.exists(source_path)

        lib = MediaLibrary()
        # Must not raise — the count reflects "rows considered", not "rows succeeded".
        count = await lib.regenerate(host=host, collection="gallery")
        assert count == 1
    finally:
        Storage.swap_manager(previous)
