"""arvel.media.library — Spatie-medialibrary-style HasMedia: attach files to a model in named
collections, with generated conversions (thumbnails)."""

from __future__ import annotations

import fsspec
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
    def __init__(self, fs: Filesystem) -> None:
        self._fs = fs

    def disk(self, name: str | None = None) -> Filesystem:
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
        assert media.model_type == "Album"
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
