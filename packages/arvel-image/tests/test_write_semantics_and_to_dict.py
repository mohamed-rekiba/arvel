"""Collection write semantics + ``to_dict`` behavior.

Covers:

- ``ConversionFailedError`` names the conversion *and* the source media id
  (and chains the wrapped exception).
- ``accept_mime_types`` rejection short-circuits BEFORE any bytes hit storage.
- ``to_dict()`` on a host without eager-loaded media has no ``media`` key and
  fires zero DB queries during serialization.
- ``to_dict()`` after ``.with_("media")`` exposes the eager-loaded rows.
- Multi-collection host's ``to_dict()`` shows only its own collection.
- ``Media.copy`` / ``Media.move`` across hosts with different ``__morph_class__``
  write the new row's ``model_type`` as the *destination's* morph class.

(``__morph_class__`` honored on read+write is covered by ``test_load_media.py``
and not duplicated here.)
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("arvel_image", reason="arvel_image is the package under test")
pytest.importorskip("PIL", reason="arvel-image depends on Pillow")

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


_HOST_CACHE: dict[str, type[Any]] = {}


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
    PILImage.new("RGBA", (8, 8), (0, 255, 0, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _multi_host() -> type[Any]:
    """Host with two collections — `avatar` (default) and `gallery`."""
    if "WsMultiHost" in _HOST_CACHE:
        return _HOST_CACHE["WsMultiHost"]

    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel_image import HasMedia, MediaCollection

    class WsMultiHost(HasMedia, Model, Timestamps):
        __tablename__ = "ws_multi_hosts"
        __media_collection__ = "avatar"

        id: int = id_()
        name: str = string(120)

        def register_media_collections(self) -> None:
            MediaCollection("avatar").register_on(self)
            MediaCollection("gallery").register_on(self)

    _HOST_CACHE["WsMultiHost"] = WsMultiHost
    return WsMultiHost


def _png_only_host() -> type[Any]:
    """Host whose `images` collection only accepts image/png."""
    if "WsPngOnly" in _HOST_CACHE:
        return _HOST_CACHE["WsPngOnly"]

    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel_image import HasMedia, MediaCollection

    class WsPngOnly(HasMedia, Model, Timestamps):
        __tablename__ = "ws_png_only_hosts"
        __media_collection__ = "images"

        id: int = id_()
        name: str = string(120)

        def register_media_collections(self) -> None:
            MediaCollection("images").accept_mime_types(["image/png"]).register_on(self)

    _HOST_CACHE["WsPngOnly"] = WsPngOnly
    return WsPngOnly


def _morph_host_a() -> type[Any]:
    """Source host — morphs as itself ("WsMorphHostA")."""
    if "WsMorphHostA" in _HOST_CACHE:
        return _HOST_CACHE["WsMorphHostA"]

    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel_image import HasMedia, MediaCollection

    class WsMorphHostA(HasMedia, Model, Timestamps):
        __tablename__ = "ws_morph_hosts_a"
        __media_collection__ = "default"

        id: int = id_()
        name: str = string(120)

        def register_media_collections(self) -> None:
            MediaCollection("default").register_on(self)
            MediaCollection("archive").register_on(self)

    _HOST_CACHE["WsMorphHostA"] = WsMorphHostA
    return WsMorphHostA


def _morph_host_b() -> type[Any]:
    """Destination host with __morph_class__='Other' — copy/move must record 'Other'."""
    if "WsMorphHostB" in _HOST_CACHE:
        return _HOST_CACHE["WsMorphHostB"]

    from arvel.database import Model, Timestamps
    from arvel.database.columns import id_, string
    from arvel_image import HasMedia, MediaCollection

    class WsMorphHostB(HasMedia, Model, Timestamps):
        __tablename__ = "ws_morph_hosts_b"
        __media_collection__ = "default"
        __morph_class__ = "Other"  # presents as a different morph alias

        id: int = id_()
        name: str = string(120)

        def register_media_collections(self) -> None:
            MediaCollection("default").register_on(self)

    _HOST_CACHE["WsMorphHostB"] = WsMorphHostB
    return WsMorphHostB


async def _create_tables(engine: AsyncEngine) -> None:
    import arvel_image
    from arvel.database import Model

    assert arvel_image.Media is not None
    _multi_host()
    _png_only_host()
    _morph_host_a()
    _morph_host_b()
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


# ─── ConversionFailedError names the media id ────────────────────────────────


async def test_conversion_failure_error_names_conversion_and_media_id(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    from arvel.facades import Storage
    from arvel_image import Conversion, MediaCollection
    from arvel_image.media.exceptions import ConversionFailedError

    await _create_tables(engine)
    Host = _multi_host()
    host = await Host.create(name="x")

    coll = MediaCollection("avatar").with_conversions(Conversion("thumb"))

    async def _boom(*, source: bytes, conversion: Conversion, context: str | None) -> bytes:
        # Mimic what the real runner produces — wrapped CFE with context.
        raise ConversionFailedError(
            f"Conversion {conversion.name!r} failed on a "
            f"{len(source)}-byte source ({context}): boom"
        )

    with (
        Storage.fake(),
        patch(
            "arvel_image.media.conversion_runner.ConversionRunner.run",
            new_callable=AsyncMock,
            side_effect=_boom,
        ),
        patch.object(host, "collection_for", return_value=coll),
        pytest.raises(ConversionFailedError) as exc,
    ):
        await host.add_image(jpeg_bytes, file_name="x.jpg")

    msg = str(exc.value)
    assert "'thumb'" in msg, "must name the conversion"
    assert "media id=" in msg, "must name the source media id"
    assert "boom" in msg, "must include the wrapped exception text"


async def test_conversion_runner_context_kwarg_flows_into_error(
    jpeg_bytes: bytes,
) -> None:
    # Unit-level: the runner itself, no DB. Forces the inner Pillow path to
    # fail (corrupt source) and checks that the optional context shows up.
    from arvel_image.media import Conversion, ConversionRunner
    from arvel_image.media.exceptions import ConversionFailedError

    runner = ConversionRunner()
    conv = Conversion("broken").format("png")

    with pytest.raises(ConversionFailedError) as exc:
        await runner.run(source=b"not an image", conversion=conv, context="media id=42")

    msg = str(exc.value)
    assert "'broken'" in msg
    assert "(media id=42)" in msg


async def test_conversion_runner_without_context_omits_parenthetical(
    jpeg_bytes: bytes,
) -> None:
    # Back-compat check: passing no context produces the original message shape.
    from arvel_image.media import Conversion, ConversionRunner
    from arvel_image.media.exceptions import ConversionFailedError

    runner = ConversionRunner()
    conv = Conversion("broken").format("png")

    with pytest.raises(ConversionFailedError) as exc:
        await runner.run(source=b"not an image", conversion=conv)

    msg = str(exc.value)
    assert "'broken'" in msg
    assert "(media id=" not in msg
    assert "12-byte source" in msg


# ─── MIME rejection short-circuits BEFORE disk write ────────────────────────


async def test_invalid_mime_rejected_before_any_disk_write(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    from arvel.facades import Storage
    from arvel_image.media.exceptions import InvalidMimeTypeError

    await _create_tables(engine)
    Host = _png_only_host()
    host = await Host.create(name="alice")

    with Storage.fake() as ctx:
        with pytest.raises(InvalidMimeTypeError) as exc:
            # JPEG bytes claiming a .png extension — content sniffer detects JPEG
            # and the png-only collection rejects it.
            await host.add_image(jpeg_bytes, file_name="lie.png")

        msg = str(exc.value)
        assert "image/jpeg" in msg, "error must name the sniffed MIME type"
        assert "lie.png" in msg, "error must name the file"

        # The disk must be untouched — no bytes leaked before validation.
        assert ctx.fake.disk().files == {}, (
            "MIME rejection must run before any storage.put() — fake disk is non-empty"
        )


# ─── to_dict() honors eager-load presence ────────────────────────────────────


async def test_to_dict_without_eager_load_omits_media_key(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    # The contract: if the eager-relation cache is empty for this host, to_dict()
    # doesn't add `media`. Mirrors what an endpoint sees when it does
    # `await Host.find(id)` (no .with_) and serializes — no surprise DB hit,
    # no surprise field. We clear the cache explicitly because add_image()
    # eagerly populates it on the writing host instance.
    from arvel.database.orm._eager import clear_eager_relation
    from arvel.facades import Storage

    await _create_tables(engine)
    Host = _multi_host()

    with Storage.fake():
        host = await Host.create(name="alice")
        await host.add_image(jpeg_bytes, file_name="a.jpg")
        clear_eager_relation(host, "media")

        out = host.to_dict()
        assert "media" not in out, (
            "to_dict() must not include `media` when the relation isn't eager-loaded"
        )


async def test_to_dict_without_eager_load_fires_zero_queries(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    from arvel.database.orm._eager import clear_eager_relation
    from arvel.facades import Storage
    from sqlalchemy import event

    await _create_tables(engine)
    Host = _multi_host()

    with Storage.fake():
        host = await Host.create(name="alice")
        await host.add_image(jpeg_bytes, file_name="a.jpg")
        clear_eager_relation(host, "media")

        count = 0

        def _before(*_a: object) -> None:
            nonlocal count
            count += 1

        event.listen(engine.sync_engine, "before_cursor_execute", _before)
        try:
            host.to_dict()
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", _before)

        assert count == 0, (
            f"to_dict() without eager-loaded media must NOT touch the DB; saw {count} queries"
        )


async def test_to_dict_with_eager_load_serializes_media(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    from arvel.facades import Storage

    await _create_tables(engine)
    Host = _multi_host()

    with Storage.fake():
        host = await Host.create(name="alice")
        await host.add_image(jpeg_bytes, file_name="a.jpg")
        await host.add_image(jpeg_bytes, file_name="b.jpg")

        loaded = await Host.with_("media").where(Host.id == host.id).first()
        assert loaded is not None
        out = loaded.to_dict()

        assert "media" in out, "to_dict() must include `media` when eager-loaded"
        assert isinstance(out["media"], list)
        assert len(out["media"]) == 2
        file_names = {m["file_name"] for m in out["media"]}
        assert file_names == {"a.jpg", "b.jpg"}


# ─── multi-collection bleed protection ───────────────────────────────────────


async def test_to_dict_filters_to_own_collection_only(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    from arvel.facades import Storage

    await _create_tables(engine)
    Host = _multi_host()

    with Storage.fake():
        host = await Host.create(name="bob")
        # Default collection is "avatar" — only this one should appear.
        await host.add_image(jpeg_bytes, file_name="avatar.jpg", collection="avatar")
        await host.add_image(jpeg_bytes, file_name="g1.jpg", collection="gallery")
        await host.add_image(jpeg_bytes, file_name="g2.jpg", collection="gallery")

        loaded = await Host.with_("media").where(Host.id == host.id).first()
        assert loaded is not None
        out = loaded.to_dict()

        assert "media" in out
        file_names = {m["file_name"] for m in out["media"]}
        assert file_names == {"avatar.jpg"}, (
            f"to_dict() bled the wrong collection — got {sorted(file_names)}; "
            "OWASP A01 / Broken Access Control regression."
        )


async def test_media_in_callable_filter_branch(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    # Covers trait.py:301 (`callable(filters)`) which the rest of the suite
    # didn't reach. Lives here because it's the same multi-collection setup.
    from arvel.facades import Storage
    from arvel_image import Media

    await _create_tables(engine)
    Host = _multi_host()

    with Storage.fake():
        host = await Host.create(name="carol")
        await host.add_image(jpeg_bytes, file_name="a.jpg", collection="gallery")
        await host.add_image(jpeg_bytes, file_name="b.jpg", collection="gallery")

        loaded = await Host.with_("media").where(Host.id == host.id).first()
        assert loaded is not None

        # `filters=` accepts either a dict or a Callable[[Media], bool].
        def _is_a(media: Media) -> bool:
            return media.file_name == "a.jpg"

        filtered = loaded.media_in("gallery", filters=_is_a)
        assert [m.file_name for m in filtered] == ["a.jpg"]
        assert all(isinstance(m, Media) for m in filtered)


# ─── copy / move across __morph_class__ writes correct type ─────────────────


async def test_media_copy_across_morph_class_uses_target_morph_alias(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    from arvel.database.orm.morph_map import get_morph_alias
    from arvel.facades import Storage

    await _create_tables(engine)
    HostA = _morph_host_a()
    HostB = _morph_host_b()

    with Storage.fake():
        src = await HostA.create(name="src")
        dst = await HostB.create(name="dst")

        original = await src.add_image(jpeg_bytes, file_name="hero.jpg")
        assert original.model_type == get_morph_alias(HostA)

        copied = await original.copy(dst, collection="default")
        assert copied.id != original.id
        assert copied.model_type == "Other", (
            "Media.copy() must record the destination's __morph_class__, "
            "not the source's morph alias."
        )
        assert copied.model_id == str(dst.id)
        # Source row must be untouched.
        from arvel_image import Media

        reloaded_src = await Media.find(original.id)
        assert reloaded_src is not None
        assert reloaded_src.model_type == get_morph_alias(HostA)


async def test_media_move_across_morph_class_updates_model_type(
    engine: AsyncEngine, session: AsyncSession, jpeg_bytes: bytes
) -> None:
    from arvel.facades import Storage

    await _create_tables(engine)
    HostA = _morph_host_a()
    HostB = _morph_host_b()

    with Storage.fake():
        src = await HostA.create(name="src")
        dst = await HostB.create(name="dst")

        original = await src.add_image(jpeg_bytes, file_name="hero.jpg")
        original_id = original.id

        moved = await original.move(dst, collection="default")
        assert moved.id == original_id, "move() updates in place, doesn't create a new row"
        assert moved.model_type == "Other"
        assert moved.model_id == str(dst.id)
        assert moved.collection_name == "default"
