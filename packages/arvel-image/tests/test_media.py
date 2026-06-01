"""Tests for the arvel-image media-library runtime.

These tests fail until ``arvel_image.media`` exists.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

import pytest

pytest.importorskip("arvel_image", reason="arvel_image is the package under test")
pytest.importorskip("PIL", reason="arvel-image depends on Pillow")

# Imported at module level so SA can resolve string-form annotations
# (``from __future__ import annotations`` stringifies ``Mapped[int]``;
# SQLAlchemy looks the name up in this module's globals).

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def jpeg_bytes_8x8() -> bytes:
    """A small JPEG used as the source for ingestion tests."""
    from PIL import Image as PILImage

    buf = io.BytesIO()
    PILImage.new("RGB", (8, 8), (255, 0, 0)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def png_bytes_4x4() -> bytes:
    """A small PNG."""
    from PIL import Image as PILImage

    buf = io.BytesIO()
    PILImage.new("RGBA", (4, 4), (0, 255, 0, 255)).save(buf, format="PNG")
    return buf.getvalue()


# ─── Unit tests ──────────────────────────────────────────────────────────────


def test_public_exports_resolve() -> None:
    """public names import."""
    from arvel_image import (
        Conversion,
        ConversionFailedError,
        HasMedia,
        Media,
        MediaCollection,
        MediaError,
        UnknownCollectionError,
    )

    for name in (
        Media,
        HasMedia,
        MediaCollection,
        Conversion,
        MediaError,
        ConversionFailedError,
        UnknownCollectionError,
    ):
        assert name is not None


def test_default_path_generator_original_layout() -> None:
    """original path is ``{id}/{file_name}``."""
    from types import SimpleNamespace

    from arvel_image.media import DefaultPathGenerator

    gen = DefaultPathGenerator()
    media = SimpleNamespace(id=42, file_name="avatar.jpg")

    assert gen.path_for(media) == "42/avatar.jpg"  # type: ignore[arg-type]


def test_default_path_generator_conversion_layout() -> None:
    """conversion path is ``{id}/conversions/{conv}-{file_name}``."""
    from types import SimpleNamespace

    from arvel_image.media import DefaultPathGenerator

    gen = DefaultPathGenerator()
    media = SimpleNamespace(id=42, file_name="avatar.jpg")

    assert gen.path_for_conversion(media, "thumb") == "42/conversions/thumb-avatar.jpg"  # type: ignore[arg-type]


def test_conversion_default_accepts_image_mime() -> None:
    """default accept matches image/*, rejects others."""
    from arvel_image.media import Conversion

    conv = Conversion("thumb")
    assert conv.accepts("image/jpeg") is True
    assert conv.accepts("image/png") is True
    assert conv.accepts("image/webp") is True
    assert conv.accepts("application/pdf") is False
    assert conv.accepts("video/mp4") is False
    assert conv.accepts("text/plain") is False


def test_conversion_apply_runs_chain_against_image(jpeg_bytes_8x8: bytes) -> None:
    """Conversion.apply chains Image ops."""
    from arvel_image import Image
    from arvel_image.media import Conversion

    src = Image.load(jpeg_bytes_8x8)
    conv = Conversion("thumb").fit("cover", 4, 4).format("png")

    out = conv.apply(src)
    out_bytes = out.to_bytes()

    from PIL import Image as PILImage

    rebuilt = PILImage.open(io.BytesIO(out_bytes))
    assert rebuilt.size == (4, 4)
    assert rebuilt.format == "PNG"


def test_media_collection_with_conversions_registers_them() -> None:
    """MediaCollection.with_conversions stores conversions."""
    from arvel_image.media import Conversion, MediaCollection

    coll = MediaCollection("avatar", single_file=True).with_conversions(
        Conversion("thumb"),
        Conversion("preview"),
    )

    names = [c.name for c in coll.conversions]
    assert names == ["thumb", "preview"]


def test_file_adder_sanitizes_path_traversal_filename() -> None:
    """../-style filenames are flattened to a basename."""
    from arvel_image.media.file_adder import FileAdder

    sanitized = FileAdder.sanitize_file_name("../../../etc/passwd")
    assert "/" not in sanitized
    assert ".." not in sanitized
    assert sanitized == "passwd"


def test_file_adder_sanitizes_control_characters() -> None:
    """control characters and NUL bytes are stripped."""
    from arvel_image.media.file_adder import FileAdder

    sanitized = FileAdder.sanitize_file_name("evil\x00name\nfoo.png")
    assert "\x00" not in sanitized
    assert "\n" not in sanitized
    assert sanitized.endswith(".png")


def test_file_adder_rejects_empty_filename() -> None:
    """empty / dot-only filenames raise."""
    from arvel_image.media import MediaError
    from arvel_image.media.file_adder import FileAdder

    for bad in ("", ".", "..", "   "):
        with pytest.raises(MediaError):
            FileAdder.sanitize_file_name(bad)


# ─── Integration tests (DB + fake storage) ───────────────────────────────────


async def _create_tables(engine: AsyncEngine) -> None:
    """Create ALL Model.metadata tables on the test engine.

    Pre-registers the cached ``User`` host class so its ``users`` table
    is on the metadata before ``create_all`` runs. Tests that use a
    different host class (e.g. ``HostBad`` in the failing-conversion
    test) declare it inline before calling this helper, so it's already
    registered by then.
    """
    from arvel.database import Model
    from arvel_image import Media

    # Touch ``Media`` so the import is not pruned: importing the symbol
    # is what registers the ``media`` table on ``Model.metadata``.
    assert Media.__tablename__ == "media"

    _host_user_class()  # ensures User is on Model.metadata

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


_USER_CACHE: dict[str, type[Any]] = {}


def _host_user_class() -> type[Any]:
    """Build a User-like model once and reuse it across tests.

    SQLAlchemy's metadata is module-level, so re-declaring a class with
    the same ``__tablename__`` raises. Each test gets its own engine via
    the ``engine`` fixture and re-runs ``Model.metadata.create_all``;
    sharing the class definition is safe and intentional.
    """
    if "User" in _USER_CACHE:
        return _USER_CACHE["User"]

    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel_image import Conversion, HasMedia, MediaCollection

    class User(Model, HasMedia, Timestamps):
        # Distinct table name avoids collision with the auth User registered
        # by packages/arvel/tests/ when the full suite runs together.
        __tablename__ = "media_test_users"

        id: int = id_()
        name: str = string(120)

        def register_media_collections(self) -> None:
            (
                MediaCollection("avatar", single_file=True)
                .with_conversions(
                    Conversion("thumb").fit("cover", 4, 4).format("png"),
                )
                .register_on(self)
            )
            MediaCollection("gallery").register_on(self)

    _USER_CACHE["User"] = User
    return User


# pytest-asyncio mode=auto picks up async tests automatically; no explicit
# pytestmark needed (would warn on the sync helpers above).


async def test_media_row_defaults_json_columns_to_empty_dict(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """JSON columns default to ``{}``, not None."""
    from arvel_image import Media

    await _create_tables(engine)

    media = await Media.create(
        model_type="User",
        model_id=1,
        collection_name="default",
        name="x",
        file_name="x.jpg",
        disk="default",
        size=10,
    )

    assert media.manipulations == {}
    assert media.custom_properties == {}
    assert media.generated_conversions == {}
    assert media.responsive_images == {}


async def test_has_media_exposes_media_morphmany(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """HasMedia gives the host a ``media`` MorphMany."""
    from arvel.facades import Storage
    from arvel_image import Media

    await _create_tables(engine)

    User = _host_user_class()
    user = await User.create(name="alice")

    with Storage.fake():
        await Media.create(
            model_type="User",
            model_id=user.id,
            collection_name="default",
            name="x",
            file_name="x.jpg",
            disk="default",
            size=10,
        )

    rows = await user.media.all()
    assert len(rows) == 1
    assert rows[0].file_name == "x.jpg"


async def test_add_media_to_collection_round_trip(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes_8x8: bytes
) -> None:
    """full ingestion round-trips to disk + media row."""
    from arvel.facades import Storage

    await _create_tables(engine)

    User = _host_user_class()
    user = await User.create(name="alice")

    with Storage.fake() as ctx:
        media = await user.add_media(jpeg_bytes_8x8, file_name="avatar.jpg").to_media_collection(
            "avatar"
        )

        assert media.id is not None
        assert media.collection_name == "avatar"
        assert media.file_name == "avatar.jpg"
        assert media.size == len(jpeg_bytes_8x8)

        # Original is on the fake disk under {id}/{file_name}
        assert ctx.fake.has_path(f"{media.id}/avatar.jpg")
        # Conversion file is also on disk under {id}/conversions/thumb-avatar.png
        # (format is png because the conversion declared .format("png"))
        assert any(p.startswith(f"{media.id}/conversions/thumb-") for p in ctx.fake.disk().files)


async def test_add_media_marks_generated_conversions(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes_8x8: bytes
) -> None:
    """a generated conversion is flagged in JSON."""
    from arvel.facades import Storage

    await _create_tables(engine)

    User = _host_user_class()
    user = await User.create(name="alice")

    with Storage.fake():
        media = await user.add_media(jpeg_bytes_8x8, file_name="avatar.jpg").to_media_collection(
            "avatar"
        )

    assert media.generated_conversions.get("thumb") is True


async def test_get_media_url_returns_disk_url(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes_8x8: bytes
) -> None:
    """get_media_url proxies to the storage disk."""
    from arvel.facades import Storage

    await _create_tables(engine)

    User = _host_user_class()
    user = await User.create(name="alice")

    with Storage.fake():
        await user.add_media(jpeg_bytes_8x8, file_name="avatar.jpg").to_media_collection("avatar")

        original_url = await user.get_media_url("avatar")
        thumb_url = await user.get_media_url("avatar", "thumb")

    assert original_url is not None
    assert original_url.startswith("memory:///")
    assert original_url.endswith("/avatar.jpg")
    assert thumb_url is not None
    assert "/conversions/thumb-" in thumb_url


async def test_get_media_filters_by_collection(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes_8x8: bytes
) -> None:
    """get_media returns only rows in the requested collection."""
    from arvel.facades import Storage

    await _create_tables(engine)

    User = _host_user_class()
    user = await User.create(name="alice")

    with Storage.fake():
        await user.add_media(jpeg_bytes_8x8, file_name="a.jpg").to_media_collection("avatar")
        await user.add_media(jpeg_bytes_8x8, file_name="g1.jpg").to_media_collection("gallery")
        await user.add_media(jpeg_bytes_8x8, file_name="g2.jpg").to_media_collection("gallery")

    avatar = await user.get_media("avatar")
    gallery = await user.get_media("gallery")
    assert len(avatar) == 1
    assert len(gallery) == 2


async def test_clear_media_collection_deletes_rows_and_files(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes_8x8: bytes
) -> None:
    """clear_media_collection deletes rows and files on disk."""
    from arvel.facades import Storage
    from arvel_image import Media

    await _create_tables(engine)

    User = _host_user_class()
    user = await User.create(name="alice")

    with Storage.fake() as ctx:
        m1 = await user.add_media(jpeg_bytes_8x8, file_name="a.jpg").to_media_collection("avatar")
        m1_path = f"{m1.id}/a.jpg"
        assert ctx.fake.has_path(m1_path)

        deleted = await user.clear_media_collection("avatar")

        assert deleted == 1
        assert not ctx.fake.has_path(m1_path)
        rows = await Media.where(Media.model_type == "User", Media.model_id == user.id).all()
        assert rows == []


async def test_single_file_collection_replaces_previous(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes_8x8: bytes
) -> None:
    """single_file collection replaces the previous media on add."""
    from arvel.facades import Storage

    await _create_tables(engine)

    User = _host_user_class()
    user = await User.create(name="alice")

    with Storage.fake() as ctx:
        first = await user.add_media(jpeg_bytes_8x8, file_name="first.jpg").to_media_collection(
            "avatar"
        )
        second = await user.add_media(jpeg_bytes_8x8, file_name="second.jpg").to_media_collection(
            "avatar"
        )

        # First file is gone
        assert not ctx.fake.has_path(f"{first.id}/first.jpg")
        # Second file is present
        assert ctx.fake.has_path(f"{second.id}/second.jpg")

    avatars = await user.get_media("avatar")
    assert len(avatars) == 1
    assert avatars[0].id == second.id


async def test_media_delete_removes_files(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes_8x8: bytes
) -> None:
    """Media.delete removes original and conversion files from disk."""
    from arvel.facades import Storage

    await _create_tables(engine)

    User = _host_user_class()
    user = await User.create(name="alice")

    with Storage.fake() as ctx:
        media = await user.add_media(jpeg_bytes_8x8, file_name="x.jpg").to_media_collection(
            "avatar"
        )
        original_path = f"{media.id}/x.jpg"
        conversion_path_prefix = f"{media.id}/conversions/"
        assert ctx.fake.has_path(original_path)
        assert any(p.startswith(conversion_path_prefix) for p in ctx.fake.disk().files)

        await media.delete()

        assert not ctx.fake.has_path(original_path)
        assert not any(p.startswith(conversion_path_prefix) for p in ctx.fake.disk().files)


async def test_media_delete_succeeds_when_file_missing(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes_8x8: bytes
) -> None:
    """best-effort cleanup."""
    from arvel.facades import Storage

    await _create_tables(engine)

    User = _host_user_class()
    user = await User.create(name="alice")

    with Storage.fake() as ctx:
        media = await user.add_media(jpeg_bytes_8x8, file_name="x.jpg").to_media_collection(
            "avatar"
        )

        # Manually nuke the file out from under the row, simulating a stale row
        await ctx.fake.disk().delete(f"{media.id}/x.jpg")

        # Delete should still succeed
        await media.delete()


async def test_non_image_media_skips_image_conversions(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """Non-image MIME skips image conversions."""
    from arvel.facades import Storage

    await _create_tables(engine)

    User = _host_user_class()
    user = await User.create(name="alice")

    with Storage.fake():
        media = await user.add_media(
            b"%PDF-1.4 fake pdf body",
            file_name="report.pdf",
        ).to_media_collection("gallery")

    # No 'thumb' conversion ran (pdf doesn't match image/*) — even if 'gallery'
    # had no conversions, we still verify the JSON is empty / absent of a
    # conversion entry.
    assert media.generated_conversions == {} or media.generated_conversions.get("thumb") is not True


async def test_failing_conversion_raises_and_leaves_no_partial_file(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes_8x8: bytes
) -> None:
    """Failing conversion raises and leaves no partial file on disk."""
    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel.facades import Storage
    from arvel_image import Conversion, ConversionFailedError, HasMedia, MediaCollection

    class _Boom(Conversion):
        def apply(self, source: Any) -> Any:
            raise RuntimeError("boom")

    class HostBad(Model, HasMedia, Timestamps):
        __tablename__ = "boom_hosts"

        id: int = id_()
        name: str = string(120)

        def register_media_collections(self) -> None:
            (
                MediaCollection("avatar", single_file=True)
                .with_conversions(_Boom("thumb"))
                .register_on(self)
            )

    await _create_tables(engine)
    host = await HostBad.create(name="x")

    with Storage.fake() as ctx:
        with pytest.raises(ConversionFailedError):
            await host.add_media(jpeg_bytes_8x8, file_name="x.jpg").to_media_collection("avatar")

        # No conversion file should be left behind
        assert not any(
            p.startswith("conversions/") or "/conversions/" in p for p in ctx.fake.disk().files
        )


async def test_image_provider_binds_path_generator_and_runner(
    tmp_path: Any,
) -> None:
    """ImageServiceProvider.register() binds PathGenerator + ConversionRunner."""
    from arvel import Application
    from arvel_image import ImageServiceProvider
    from arvel_image.media import ConversionRunner, DefaultPathGenerator, PathGenerator

    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([ImageServiceProvider])
        .create()
    )
    await app.boot()

    # ``Container.make(abstract: type[T])`` — strict mypy refuses abstract
    # classes (``PathGenerator`` is an ``abc.ABC``, used here as a DI
    # binding key, not a class to instantiate directly). Carrying it
    # through an ``Any``-typed local sidesteps the strict check while
    # preserving the runtime resolution path; the ``isinstance`` assertion
    # below is the actual contract under test.
    path_generator_key: Any = PathGenerator
    gen = app.container.make(path_generator_key)
    runner = app.container.make(ConversionRunner)
    assert isinstance(gen, DefaultPathGenerator)
    assert isinstance(runner, ConversionRunner)


def test_arvel_image_does_not_shell_out() -> None:
    """source contains no subprocess / os.system import.

    Extends the same arch test from the suite to cover the new
    runtime modules.
    """
    from pathlib import Path

    import arvel_image

    src = Path(arvel_image.__file__).parent
    forbidden = ("import subprocess", "from subprocess", "os.system(")
    for py in src.rglob("*.py"):
        text = py.read_text()
        for token in forbidden:
            assert token not in text, f"{py} contains forbidden {token}"
