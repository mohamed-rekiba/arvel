"""arvel.media.library — attach files to models, à la Spatie's medialibrary.

A model that mixes in:class:`HasMedia` can ``add_media(...).to_media_collection("images")``; each
file becomes a:class:`Media` row (the ``media`` table) stored on a Storage disk. Override
``register_media_conversions`` to derive versions (thumbnails, resized/re-encoded copies) that are
generated on upload and addressable by name via ``media.get_url("thumb")``.

Not part of the original ch-08 port spec — added on request, following the Spatie design.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any, ClassVar, cast

from arvel.database import Model, morph_type_of

if TYPE_CHECKING:
    from arvel.media import Image


class MediaConversion:
    """A named derived version of a media file — resize and/or re-encode (Spatie conversion)."""

    def __init__(
        self,
        name: str,
        *,
        width: int | None = None,
        height: int | None = None,
        fmt: str = "PNG",
    ) -> None:
        self.name = name
        self.width = width
        self.height = height
        self.fmt = fmt

    def apply(self, image: Image) -> bytes:
        """Produce the conversion's bytes from the source image."""
        result = image
        if self.width is not None and self.height is not None:
            result = image.resize(self.width, self.height)
        if self.fmt.upper() in ("JPEG", "JPG"):
            # JPEG has no alpha channel; flatten RGBA/P/LA to RGB first or Pillow raises.
            result = result.convert("RGB")
        return result.encode(self.fmt)


class Media(Model):
    """A single stored file attached to a model (row in ``media``)."""

    __table_name__ = "media"
    __fields__: ClassVar[dict[str, Any]] = {
        "model_type": str,
        "model_id": int,
        "collection_name": str,
        "name": str,
        "file_name": str,
        "mime_type": str,
        "disk": str,
        "size": int,
        "custom_properties": dict,
        "generated_conversions": dict,
        "order_column": int,
    }
    __fillable__: ClassVar[list[str]] = list(__fields__)
    __casts__: ClassVar[dict[str, str]] = {
        "custom_properties": "json",
        "generated_conversions": "json",
    }

    def _conversions(self) -> dict[str, Any]:
        gc = self.generated_conversions
        return cast("dict[str, Any]", gc) if isinstance(gc, dict) else {}

    def has_generated_conversion(self, name: str) -> bool:
        return name in self._conversions()

    def stored_paths(self) -> list[str]:
        """Every disk path this media owns — the original plus each generated conversion."""
        paths = [self.get_path(), *self._conversions().values()]
        return [path for path in paths if path is not None]

    def get_path(self, conversion: str | None = None) -> str | None:
        """Disk-relative path to the original file, or a named conversion (``None`` if absent)."""
        if conversion is not None:
            path: str | None = self._conversions().get(conversion)
            return path
        return f"{self.collection_name}/{self.id}/{self.file_name}"

    def get_url(self, conversion: str | None = None) -> str | None:
        """Public URL — the disk's configured ``url`` base + the path, else the path itself."""
        path = self.get_path(conversion)
        if path is None:
            return None
        from arvel.kernel import app, has_application
        from arvel.kernel.config import config

        base = ""
        if has_application() and app().bound("config"):
            base = config(f"filesystems.disks.{self.disk}.url", "") or ""
        return f"{base.rstrip('/')}/{path}" if base else path


class MediaAdder:
    """Fluent builder returned by ``HasMedia.add_media`` — terminated by ``to_media_collection``."""

    def __init__(self, model: Any, contents: bytes, file_name: str, mime_type: str | None) -> None:
        self._model = model
        self._contents = contents
        self._file_name = file_name
        self._mime_type = mime_type or ""
        self._name = file_name
        self._custom: dict[str, Any] = {}

    def using_name(self, name: str) -> MediaAdder:
        self._name = name
        return self

    def with_custom_properties(self, properties: dict[str, Any]) -> MediaAdder:
        self._custom = dict(properties)
        return self

    _IMAGE_EXTS: ClassVar[frozenset[str]] = frozenset(
        {"png", "jpg", "jpeg", "gif", "webp", "bmp", "tiff", "tif"}
    )

    def _is_image(self) -> bool:
        """Whether conversions apply — by mime type, or (when absent) the file extension."""
        if self._mime_type:
            return self._mime_type.startswith("image/")
        ext = self._file_name.rsplit(".", 1)[-1].lower() if "." in self._file_name else ""
        return ext in self._IMAGE_EXTS

    async def to_media_collection(
        self, collection: str = "default", *, disk: str | None = None
    ) -> Media:
        """Store the file (and its conversions) on ``disk`` (``None`` = the configured default
        disk) and record a:class:`Media` row.

        The **resolved** disk name is what's persisted on the row — ``get_url``/``delete_media``
        later read config and re-resolve the disk by that stored name, so a placeholder would
        break every downstream path.

        The disk is resolved BEFORE the row is written — an unknown/misconfigured disk fails
        inside the no-orphan guarantee, never after the reservation exists. The row is created
        first (its id names the storage path — ``{collection}/{id}/...``), but
        it's a reservation, not a commit: if any store write below fails, every file written so
        far is cleaned up and the row itself is deleted, so a disk error never leaves an orphan
        row (with no file) or an orphan file (with no row)."""
        from arvel.kernel import app
        from arvel.telemetry import span

        model = self._model
        media_model: type[Media] = model.__media_model__
        disks = app("filesystem")
        # only None means "use the default"; an explicit name goes to the manager to validate.
        # A blank name is rejected HERE: the manager's own `name or default` fallback would
        # accept it, but the row would then persist disk="" and poison get_url/delete later.
        if disk is not None and not disk.strip():
            message = "disk name must not be blank (omit disk= to use the default disk)"
            raise ValueError(message)
        disk_name = disks.default_driver() if disk is None else disk
        # resolve the filesystem BEFORE the row exists: an unknown/misconfigured disk must fail
        # here, inside the no-orphan guarantee, not after the reservation row was written
        filesystem = disks.disk(disk_name)
        existing = await model.get_media(collection)
        media = await media_model.create(
            model_type=morph_type_of(type(model)),
            model_id=model.id,
            collection_name=collection,
            name=self._name,
            file_name=self._file_name,
            mime_type=self._mime_type,
            disk=disk_name,
            size=len(self._contents),
            custom_properties=self._custom,
            generated_conversions={},
            order_column=len(existing) + 1,
        )
        base_dir = f"{collection}/{media.id}"
        written: list[str] = []
        try:
            original_path = f"{base_dir}/{self._file_name}"
            with span("media store", kind="client", attributes={"media.op": "store"}):
                await filesystem.put(original_path, self._contents)
            written.append(original_path)

            # Conversions are image transforms (PIL); non-image files are stored as-is, untouched.
            conversions = model.register_media_conversions()
            if conversions and self._is_image():
                from anyio.to_thread import run_sync

                from arvel.media import Image

                # PIL decode/transform is CPU-bound — keep it off the event loop
                source = await run_sync(Image.open, self._contents)
                generated: dict[str, str] = {}
                for conversion in conversions:
                    path = f"{base_dir}/conversions/{conversion.name}.{conversion.fmt.lower()}"
                    with span("media store", kind="client", attributes={"media.op": "store"}):
                        await filesystem.put(path, await run_sync(conversion.apply, source))
                    written.append(path)
                    generated[conversion.name] = path
                media.generated_conversions = generated
                await media.save()
        except Exception:
            # best-effort cleanup: a secondary failure (permissions, network) must not stop
            # the remaining paths or the row removal — the ORIGINAL error is what propagates
            for path in written:
                with contextlib.suppress(Exception):
                    await filesystem.delete(path)
            with contextlib.suppress(Exception):
                await media.delete()
            raise
        return media


class HasMedia:
    """Mixin: attach files to a model via named media collections (the familiar media-collections mixin).

    Override:meth:`register_media_conversions` to declare derived versions generated on upload.
    Override ``__media_model__`` to store media as a custom:class:`Media` subclass (e.g. one that
    adds conversion accessors); it must keep ``__table_name__ = "media"``.
    """

    __media_model__: ClassVar[type[Media]] = Media

    def register_media_conversions(self) -> list[MediaConversion]:
        """Return the conversions to generate for each added file (default: none)."""
        return []

    def add_media(
        self, contents: bytes, *, file_name: str, mime_type: str | None = None
    ) -> MediaAdder:
        """Begin attaching ``contents`` (raw bytes) under ``file_name``."""
        return MediaAdder(self, contents, file_name, mime_type)

    def media(self) -> Any:
        """The model's media as a polymorphic relation — eager-loadable in one batched query via
        ``Model.with_("media")`` (no N+1 across a list of models)."""
        return self.morph_many(self.__media_model__, "model")  # type: ignore[attr-defined]

    async def get_media(self, collection: str = "default") -> list[Media]:
        """All media in ``collection`` for this model, in order. Uses the eager-loaded ``media``
        relation (``with_("media")``) when present — filtered in memory, no extra query."""
        loaded = cast("list[Media] | None", self.relation("media"))  # type: ignore[attr-defined]
        if loaded is not None:
            in_collection = [m for m in loaded if m.collection_name == collection]
            in_collection.sort(key=lambda m: m.order_column)
            return in_collection
        rows = await (
            self.__media_model__.where(model_type=morph_type_of(type(self)))
            .where(model_id=self.id)  # type: ignore[attr-defined]
            .where(collection_name=collection)
            .order_by("order_column")
            .get()
        )
        return cast("list[Media]", rows)

    async def get_first_media(self, collection: str = "default") -> Media | None:
        items = await self.get_media(collection)
        return items[0] if items else None

    async def get_first_media_url(
        self, collection: str = "default", conversion: str | None = None
    ) -> str | None:
        media = await self.get_first_media(collection)
        return media.get_url(conversion) if media is not None else None

    async def delete_media(self, media_id: int) -> bool:
        """Delete ONE media item this model owns — the row plus every stored file (original +
        conversions; Spatie ``deleteMedia`` parity). Returns ``False`` when the id isn't attached
        to THIS model, so a caller can never remove another model's media through it."""
        from arvel.kernel import app
        from arvel.telemetry import span

        media_model = getattr(type(self), "__media_model__", Media)
        media = await media_model.find(media_id)
        if (
            media is None
            or media.model_type != morph_type_of(type(self))
            or media.model_id != getattr(self, "id", None)
        ):
            return False
        disk = app("filesystem").disk(media.disk)
        for path in media.stored_paths():
            with span("media delete", kind="client", attributes={"media.op": "delete"}):
                await disk.delete(path)  # already idempotent — no exists() round-trip needed
        await media.delete()
        return True

    async def clear_media_collection(self, collection: str = "default") -> None:
        """Delete every media item in ``collection`` (rows + stored files)."""
        from arvel.kernel import app
        from arvel.telemetry import span

        for media in await self.get_media(collection):
            disk = app("filesystem").disk(media.disk)
            for path in media.stored_paths():
                with span("media delete", kind="client", attributes={"media.op": "delete"}):
                    await disk.delete(path)  # already idempotent
            await media.delete()


__all__ = ["HasMedia", "Media", "MediaAdder", "MediaConversion"]
