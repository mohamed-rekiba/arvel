"""arvel.media.library — HasMedia attaches files to a model in named collections with generated
conversions (thumbnails)."""

from __future__ import annotations

from typing import Any

import fsspec
import pytest
import sqlalchemy as sa

from arvel import Attribute
from arvel.database import ConnectionResolver, Model
from arvel.filesystem import Filesystem
from arvel.kernel.application import Application
from arvel.media import HasMedia, Image, Media, MediaConversion


class Album(HasMedia, Model):
    __fields__ = {"title": str}
    __fillable__ = ["title"]

    def register_media_conversions(self) -> list[MediaConversion]:
        return [MediaConversion("thumb", width=10, height=10, fmt="PNG")]


class Doc(HasMedia, Model):  # a second media owner — to test polymorphic isolation
    __fields__ = {"name": str}
    __fillable__ = ["name"]


class PostMedia(Media):  # a custom media model with app-specific URL accessors (user-defined)
    __table_name__ = "media"
    __appends__ = ["url", "thumb"]

    def url(self) -> Attribute:
        return Attribute(get=lambda value, attrs: self.get_url())

    def thumb(self) -> Attribute:
        return Attribute(get=lambda value, attrs: self.get_url("thumb"))


class Gallery(HasMedia, Model):
    __media_model__ = PostMedia
    __fields__ = {"title": str}
    __fillable__ = ["title"]

    def register_media_conversions(self) -> list[MediaConversion]:
        return [MediaConversion("thumb", width=10, height=10, fmt="PNG")]


class _Disks:
    """Test double for the FilesystemManager: one in-memory disk named "memory". It mirrors the
    real manager's contract (a *name is resolved*, the default has a real name) so it can't hide
    a bad disk sentinel the way an ignore-the-name fake once did."""

    def __init__(self, fs: Filesystem) -> None:
        self._fs = fs

    def default_driver(self) -> str:
        return "memory"

    def disk(self, name: str | None = None) -> Filesystem:
        assert name in (None, "memory"), f"unknown disk {name!r}"
        return self._fs


async def _setup() -> tuple[Filesystem, ConnectionResolver]:
    app = Application.configure().create()
    fs = Filesystem(fsspec.filesystem("memory"))
    app.instance("filesystem", _Disks(fs))
    db = ConnectionResolver()
    Media.set_connection(db)
    Album.set_connection(db)
    await db.execute(sa.schema.CreateTable(Media.__table__))
    await db.execute(sa.schema.CreateTable(Album.__table__))
    return fs, db


def _png() -> bytes:
    return Image.make(20, 20, "red").encode("PNG")


async def test_add_media_stores_file_and_row() -> None:
    fs, db = await _setup()
    try:
        album = await Album.create(title="trip")
        media = await album.add_media(
            _png(), file_name="a.png", mime_type="image/png"
        ).to_media_collection("images")
        assert media.collection_name == "images"
        from arvel.database import morph_type_of

        assert media.model_type == morph_type_of(Album)
        assert media.model_id == album.id
        assert media.size > 0
        assert await fs.exists(media.get_path())
    finally:
        await db.dispose()


async def test_conversion_is_generated() -> None:
    fs, db = await _setup()
    try:
        album = await Album.create(title="trip")
        media = await album.add_media(_png(), file_name="a.png").to_media_collection("images")
        assert media.has_generated_conversion("thumb")
        thumb_path = media.get_path("thumb")
        assert thumb_path is not None
        assert await fs.exists(thumb_path)
        thumb = Image.open(await fs.get(thumb_path))
        assert (thumb.width, thumb.height) == (10, 10)
    finally:
        await db.dispose()


async def test_get_media_ordered_and_first_url() -> None:
    _fs, db = await _setup()
    try:
        album = await Album.create(title="t")
        await album.add_media(_png(), file_name="a.png").to_media_collection("images")
        await album.add_media(_png(), file_name="b.png").to_media_collection("images")
        items = await album.get_media("images")
        assert [m.file_name for m in items] == ["a.png", "b.png"]
        assert [m.order_column for m in items] == [1, 2]
        assert await album.get_first_media_url("images") == f"images/{items[0].id}/a.png"
    finally:
        await db.dispose()


async def test_clear_media_collection_removes_rows_and_files() -> None:
    fs, db = await _setup()
    try:
        album = await Album.create(title="t")
        media = await album.add_media(_png(), file_name="a.png").to_media_collection("images")
        path = media.get_path()
        await album.clear_media_collection("images")
        assert await album.get_media("images") == []
        assert path is not None
        assert not await fs.exists(path)
    finally:
        await db.dispose()


async def test_delete_media_removes_one_item_and_guards_ownership() -> None:
    """delete_media removes only that item's row + files, never another model's media."""
    fs, db = await _setup()
    try:
        album = await Album.create(title="t")
        keep = await album.add_media(_png(), file_name="keep.png").to_media_collection("images")
        gone = await album.add_media(_png(), file_name="gone.png").to_media_collection("images")
        gone_paths = list(gone.stored_paths())

        assert await album.delete_media(gone.id) is True
        remaining = await album.get_media("images")
        assert [m.id for m in remaining] == [keep.id]
        for path in gone_paths:
            assert not await fs.exists(path)

        # a DIFFERENT owner cannot delete the album's media
        other = await Album.create(title="other")
        assert await other.delete_media(keep.id) is False
        assert [m.id for m in await album.get_media("images")] == [keep.id]
    finally:
        await db.dispose()


async def test_non_image_media_stores_without_conversions() -> None:
    # Album registers an image "thumb" conversion; a video must still attach (no PIL decode).
    fs, db = await _setup()
    try:
        album = await Album.create(title="trip")
        media = await album.add_media(
            b"\x00\x00not-an-image", file_name="clip.mp4", mime_type="video/mp4"
        ).to_media_collection("videos")
        assert media.mime_type == "video/mp4"
        assert media.generated_conversions == {}
        assert media.has_generated_conversion("thumb") is False
        assert await fs.exists(media.get_path())  # original stored, no crash
    finally:
        await db.dispose()


async def test_with_media_eager_loads_in_one_batch() -> None:
    _fs, db = await _setup()
    try:
        a = await Album.create(title="a")
        b = await Album.create(title="b")
        await a.add_media(_png(), file_name="a1.png").to_media_collection("images")
        await b.add_media(_png(), file_name="b1.png").to_media_collection("images")

        albums = {al.title: al for al in await Album.with_("media").get()}
        assert albums["a"].relation("media") is not None  # eager-loaded, no per-model query
        # get_media reads the loaded relation (no extra query) and filters by collection
        assert [m.file_name for m in await albums["a"].get_media("images")] == ["a1.png"]
        assert [m.file_name for m in await albums["b"].get_media("images")] == ["b1.png"]
    finally:
        await db.dispose()


async def test_eager_load_is_polymorphic_isolated() -> None:
    _fs, db = await _setup()
    try:
        Doc.set_connection(db)
        await db.execute(sa.schema.CreateTable(Doc.__table__))
        album = await Album.create(title="a")  # id 1
        doc = await Doc.create(name="d")  # id 1 in its own table
        await album.add_media(_png(), file_name="album.png").to_media_collection("images")
        await doc.add_media(_png(), file_name="doc.png").to_media_collection("images")

        [loaded] = await Album.with_("media").get()
        names = [m.file_name for m in (loaded.relation("media") or [])]
        assert names == ["album.png"]  # NOT doc.png, despite the shared id
    finally:
        await db.dispose()


async def test_constrained_eager_load_one_collection() -> None:
    _fs, db = await _setup()
    try:
        album = await Album.create(title="a")
        await album.add_media(_png(), file_name="img.png").to_media_collection("images")
        await album.add_media(_png(), file_name="clip.mp4").to_media_collection("videos")

        # constrain the eager load to a single collection — only "images" is fetched in the batch
        [loaded] = await Album.with_(media=lambda q: q.where(collection_name="images")).get()
        names = [m.file_name for m in (loaded.relation("media") or [])]
        assert names == ["img.png"]
    finally:
        await db.dispose()


async def test_custom_media_model_with_user_accessors() -> None:
    _fs, db = await _setup()
    try:
        PostMedia.set_connection(db)  # shares the "media" table created in _setup
        Gallery.set_connection(db)
        await db.execute(sa.schema.CreateTable(Gallery.__table__))

        gallery = await Gallery.create(title="g")
        media = await gallery.add_media(_png(), file_name="a.png").to_media_collection("images")
        assert isinstance(media, PostMedia)  # __media_model__ honored on write
        # user-defined accessors on the subclass
        assert media.url == media.get_url()
        assert media.thumb == media.get_url("thumb")
        # appended → carried in serialization out of the box
        assert media.to_dict()["url"] == media.get_url()
        assert media.to_dict()["thumb"] == media.get_url("thumb")

        [loaded] = await gallery.get_media("images")
        assert isinstance(loaded, PostMedia)  # ...and on read
        assert loaded.thumb is not None
    finally:
        await db.dispose()


class _FailingDisk:
    """Wraps a real ``Filesystem``, raising on its ``put``'s ``fail_after``'th call — a
    fault-injection stub for the write-then-row cleanup path. Records every successful ``put``
    and ``delete`` so a test can assert the cleanup path deleted exactly what it wrote, without
    depending on fsspec's process-wide "memory" filesystem being otherwise empty."""

    def __init__(self, fs: Filesystem, *, fail_after: int) -> None:
        self._fs = fs
        self._fail_after = fail_after
        self.put_calls = 0
        self.written: list[str] = []
        self.deleted: list[str] = []

    async def put(self, path: str, contents: bytes) -> str:
        self.put_calls += 1
        if self.put_calls > self._fail_after:
            raise OSError("disk full (fault injection)")
        result = await self._fs.put(path, contents)
        self.written.append(path)
        return result

    async def delete(self, path: str) -> bool:
        self.deleted.append(path)
        return await self._fs.delete(path)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._fs, name)


class _FailingDisks:
    def __init__(self, disk: _FailingDisk) -> None:
        self._disk = disk

    def default_driver(self) -> str:
        return "memory"

    def disk(self, name: str | None = None) -> _FailingDisk:
        return self._disk


async def test_a_failed_original_write_leaves_no_orphan_row_or_file() -> None:
    app = Application.configure().create()
    fs = Filesystem(fsspec.filesystem("memory"))
    failing = _FailingDisk(fs, fail_after=0)  # the very first put() (the original) raises
    app.instance("filesystem", _FailingDisks(failing))
    db = ConnectionResolver()
    Media.set_connection(db)
    Album.set_connection(db)
    await db.execute(sa.schema.CreateTable(Media.__table__))
    await db.execute(sa.schema.CreateTable(Album.__table__))
    try:
        album = await Album.create(title="trip")
        with pytest.raises(OSError, match="disk full"):
            await album.add_media(_png(), file_name="a.png").to_media_collection("images")

        assert await album.get_media("images") == []  # no orphan row
        assert failing.written == []  # the very first put failed before writing anything
        assert failing.deleted == []  # nothing to clean up either
    finally:
        await db.dispose()


async def test_a_failed_conversion_write_cleans_up_the_original_file_and_the_row() -> None:
    app = Application.configure().create()
    fs = Filesystem(fsspec.filesystem("memory"))
    failing = _FailingDisk(fs, fail_after=1)  # the original succeeds; the conversion raises
    app.instance("filesystem", _FailingDisks(failing))
    db = ConnectionResolver()
    Media.set_connection(db)
    Album.set_connection(db)  # Album registers a "thumb" conversion
    await db.execute(sa.schema.CreateTable(Media.__table__))
    await db.execute(sa.schema.CreateTable(Album.__table__))
    try:
        album = await Album.create(title="trip")
        with pytest.raises(OSError, match="disk full"):
            await album.add_media(_png(), file_name="a.png").to_media_collection("images")

        assert await album.get_media("images") == []  # no orphan row
        # the original write (put #1) succeeded before the conversion write (put #2) raised —
        # the cleanup path must have deleted it, not just left the row alone
        assert failing.written == ["images/1/a.png"]
        assert failing.deleted == ["images/1/a.png"]
    finally:
        await db.dispose()


def test_jpeg_conversion_flattens_rgba_source() -> None:
    """JPEG has no alpha channel, so the pipeline must flatten an RGBA source before encoding."""
    from io import BytesIO

    from PIL import Image as PILImage

    buf = BytesIO()
    PILImage.new("RGBA", (20, 20), (120, 90, 100, 128)).save(buf, format="PNG")
    source = Image.open(buf.getvalue())

    out = MediaConversion("web", width=10, height=10, fmt="JPEG").apply(source)

    assert PILImage.open(BytesIO(out)).format == "JPEG"


async def test_add_media_without_disk_uses_the_configured_default_disk(tmp_path: Any) -> None:
    """The documented primary path — ``add_media(...).to_media_collection(...)`` with no
    ``disk=`` — must resolve the *configured* default disk through the real FilesystemManager
    and persist that disk's real name on the row (so get_url/delete read the right config)."""
    from arvel.filesystem import FilesystemManager

    app = Application.configure().create()
    app.make("config").set(
        "filesystems", {"default": "local", "disks": {"local": {"root": str(tmp_path)}}}
    )
    app.instance("filesystem", FilesystemManager())
    db = ConnectionResolver()
    Media.set_connection(db)
    Album.set_connection(db)
    await db.execute(sa.schema.CreateTable(Media.__table__))
    await db.execute(sa.schema.CreateTable(Album.__table__))
    try:
        album = await Album.create(title="trip")
        media = await album.add_media(b"hello", file_name="notes.txt").to_media_collection()
        assert media.disk == "local"  # the resolved disk name, never a "default" placeholder
        stored = tmp_path / "default" / str(media.id) / "notes.txt"
        assert stored.exists()
        assert await album.delete_media(media.id) is True  # delete resolves the same disk
        assert not stored.exists()
    finally:
        await db.dispose()


async def test_an_unresolvable_disk_fails_before_any_row_is_written(tmp_path: Any) -> None:
    """The no-orphan guarantee must cover disk RESOLUTION too: an explicitly bogus disk= used
    to raise only after the Media row was created (and outside the cleanup scope), leaving an
    orphaned row with no file."""
    from arvel.filesystem import FilesystemManager

    app = Application.configure().create()
    app.make("config").set(
        "filesystems", {"default": "local", "disks": {"local": {"root": str(tmp_path)}}}
    )
    app.instance("filesystem", FilesystemManager())
    db = ConnectionResolver()
    Media.set_connection(db)
    Album.set_connection(db)
    await db.execute(sa.schema.CreateTable(Media.__table__))
    await db.execute(sa.schema.CreateTable(Album.__table__))
    try:
        album = await Album.create(title="trip")
        with pytest.raises(Exception, match="nope"):
            await album.add_media(b"x", file_name="x.txt").to_media_collection(disk="nope")
        assert await Media.all() == []  # no orphaned reservation row

        # an explicit empty string is INVALID input, not "use the default" — it must fail
        # loudly (and, per the guarantee above, leave no row)
        with pytest.raises(ValueError, match="blank"):
            await album.add_media(b"x", file_name="x.txt").to_media_collection(disk="")
        assert await Media.all() == []
    finally:
        await db.dispose()
