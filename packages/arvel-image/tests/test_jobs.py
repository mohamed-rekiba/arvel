"""QueuedConversionJob.handle() — async conversion pipeline tests."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, ClassVar

import pytest

pytest.importorskip("arvel_image", reason="arvel_image is the package under test")
pytest.importorskip("PIL", reason="arvel-image depends on Pillow")

# Host class must live at module level so importlib.import_module(__name__) can
# find it — that's how QueuedConversionJob rehydrates its host at execution time.
from arvel.database import Model, Timestamps
from arvel.database.columns import id_, string
from arvel_image import HasMedia, MediaCollection
from arvel_image.media.conversion import Conversion

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class JobHost(HasMedia, Model, Timestamps):
    __tablename__ = "media_jobs_hosts"
    __media_collection__ = "images"

    id: int = id_()
    name: str = string(120)

    __arvel_media_collections__: ClassVar[dict[str, MediaCollection]] = {}
    __arvel_collections_registered__: ClassVar[bool] = False

    def register_media_collections(self) -> None:
        (
            MediaCollection("images")
            .with_conversions(Conversion("thumb").fit("cover", 4, 4).format("png"))
            .register_on(self)
        )


@pytest.fixture
def jpeg_bytes_8x8() -> bytes:
    from PIL import Image as PILImage

    buf = io.BytesIO()
    PILImage.new("RGB", (8, 8), (50, 100, 150)).save(buf, format="JPEG", quality=95)
    return buf.getvalue()


@pytest.fixture
def large_jpeg_bytes() -> bytes:
    """Large enough for the responsive width calculator to emit variants."""
    from PIL import Image as PILImage

    buf = io.BytesIO()
    PILImage.new("RGB", (500, 375), (60, 120, 180)).save(buf, format="JPEG", quality=95)
    return buf.getvalue()


async def _create_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def _seed(host: JobHost, contents: bytes) -> tuple[Media, str]:
    """Create a Media row + write the source bytes to the disk that the job will read."""
    from arvel.facades import Storage
    from arvel_image.media.model import Media as _Media
    from arvel_image.media.path_generator import get_path_generator

    m = await _Media.create(
        model_type="JobHost",
        model_id=str(host.id),
        collection_name="images",
        name="src",
        file_name="src.jpg",
        disk="default",
        size=len(contents),
    )
    m.mime_type = "image/jpeg"
    await m.save()
    path = get_path_generator().path_for(m)
    await Storage.disk().put(path, contents)
    return m, path


if TYPE_CHECKING:
    from arvel_image.media.model import Media


# ── handle(): happy path ────────────────────────────────────────────────────


async def test_handle_runs_conversions(
    engine: AsyncEngine,
    session: AsyncSession,
    jpeg_bytes_8x8: bytes,
) -> None:
    """When the row + host both exist, handle() runs conversions and saves."""
    from arvel.facades import Storage
    from arvel_image.media.jobs import QueuedConversionJob

    await _create_tables(engine)
    with Storage.fake():
        host = await JobHost.create(name="happy-host")
        media, _ = await _seed(host, jpeg_bytes_8x8)

        job = QueuedConversionJob(
            media_id=str(media.id),
            model_class_path=f"{__name__}.JobHost",
        )
        await job.handle()

        reloaded = await media.fresh()
        assert reloaded is not None
        assert reloaded.generated_conversions.get("thumb") is True


# ── handle(): media row missing ─────────────────────────────────────────────


async def test_handle_silently_returns_when_media_missing(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """A deleted-before-execution media row makes handle() a no-op."""
    from arvel_image.media.jobs import QueuedConversionJob

    await _create_tables(engine)
    job = QueuedConversionJob(
        media_id="999999",
        model_class_path=f"{__name__}.JobHost",
    )
    # Must not raise.
    await job.handle()


# ── _resolve_host: error branches ───────────────────────────────────────────


async def test_handle_silently_returns_when_module_path_is_empty(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes_8x8: bytes
) -> None:
    """A bare class name (no module) skips conversion silently."""
    from arvel.facades import Storage
    from arvel_image.media.jobs import QueuedConversionJob

    await _create_tables(engine)
    with Storage.fake():
        host = await JobHost.create(name="bare-name")
        media, _ = await _seed(host, jpeg_bytes_8x8)
        job = QueuedConversionJob(media_id=str(media.id), model_class_path="JobHost")
        await job.handle()

        reloaded = await media.fresh()
        assert reloaded is not None
        # No conversion ran — `generated_conversions` stays empty.
        assert reloaded.generated_conversions == {}


async def test_handle_silently_returns_when_module_does_not_exist(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes_8x8: bytes
) -> None:
    """A nonsense module path doesn't crash the worker."""
    from arvel.facades import Storage
    from arvel_image.media.jobs import QueuedConversionJob

    await _create_tables(engine)
    with Storage.fake():
        host = await JobHost.create(name="no-module")
        media, _ = await _seed(host, jpeg_bytes_8x8)
        job = QueuedConversionJob(
            media_id=str(media.id),
            model_class_path="not_a_real_module_xyz.NoSuchClass",
        )
        await job.handle()

        reloaded = await media.fresh()
        assert reloaded is not None
        assert reloaded.generated_conversions == {}


async def test_handle_silently_returns_when_class_not_in_module(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes_8x8: bytes
) -> None:
    """Module imports but the class isn't there — silent skip."""
    from arvel.facades import Storage
    from arvel_image.media.jobs import QueuedConversionJob

    await _create_tables(engine)
    with Storage.fake():
        host = await JobHost.create(name="no-class")
        media, _ = await _seed(host, jpeg_bytes_8x8)
        job = QueuedConversionJob(
            media_id=str(media.id),
            model_class_path=f"{__name__}.NotARealClassXYZ",
        )
        await job.handle()

        reloaded = await media.fresh()
        assert reloaded is not None
        assert reloaded.generated_conversions == {}


async def test_handle_silently_returns_when_host_row_missing(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes_8x8: bytes
) -> None:
    """Class resolves but the host row was deleted — silent skip, no conversions."""
    from arvel.facades import Storage
    from arvel_image.media.jobs import QueuedConversionJob

    await _create_tables(engine)
    with Storage.fake():
        host = await JobHost.create(name="ghost-host")
        media, _ = await _seed(host, jpeg_bytes_8x8)
        await host.delete()

        job = QueuedConversionJob(
            media_id=str(media.id),
            model_class_path=f"{__name__}.JobHost",
        )
        await job.handle()

        reloaded = await media.fresh()
        assert reloaded is not None
        assert reloaded.generated_conversions == {}


# ── handle(): generate_responsive_images branch ─────────────────────────────


async def test_handle_generates_responsive_when_flag_set(
    engine: AsyncEngine, session: AsyncSession, large_jpeg_bytes: bytes
) -> None:
    """flag=True populates responsive_images["original"]."""
    from arvel.facades import Storage
    from arvel_image.media.jobs import QueuedConversionJob

    await _create_tables(engine)
    with Storage.fake():
        host = await JobHost.create(name="resp-host")
        media, _ = await _seed(host, large_jpeg_bytes)
        job = QueuedConversionJob(
            media_id=str(media.id),
            model_class_path=f"{__name__}.JobHost",
            generate_responsive_images=True,
        )
        await job.handle()

        reloaded = await media.fresh()
        assert reloaded is not None
        assert "original" in reloaded.responsive_images
        assert reloaded.responsive_images["original"].get("urls")


async def test_handle_generate_responsive_swallows_disk_read_errors(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes_8x8: bytes
) -> None:
    """When the source file is missing from disk, the regen branch returns quietly."""
    from arvel.facades import Storage
    from arvel_image.media.jobs import QueuedConversionJob
    from arvel_image.media.model import Media as _Media
    from arvel_image.media.path_generator import get_path_generator

    await _create_tables(engine)
    with Storage.fake():
        host = await JobHost.create(name="missing-file-host")
        media = await _Media.create(
            model_type="JobHost",
            model_id=str(host.id),
            collection_name="images",
            name="ghost",
            file_name="ghost.jpg",
            disk="default",
            size=0,
        )
        media.mime_type = "image/jpeg"
        await media.save()

        # Path does NOT exist on disk — Storage.fake() returns an empty store.
        path = get_path_generator().path_for(media)
        assert not await Storage.disk().exists(path)

        job = QueuedConversionJob(
            media_id=str(media.id),
            model_class_path=f"{__name__}.JobHost",
            generate_responsive_images=True,
        )
        # Must not raise.
        await job.handle()
