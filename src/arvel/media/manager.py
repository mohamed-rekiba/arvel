"""MediaManager — default MediaContract implementation backed by StorageContract.

Feature-complete media library inspired by
`Spatie Laravel Media Library <https://spatie.be/docs/laravel-medialibrary/v11>`_.
"""

from __future__ import annotations

import uuid
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from arvel.media.config import MediaSettings  # noqa: TC001
from arvel.media.contracts import MediaContract
from arvel.media.events import (
    CollectionHasBeenCleared,
    ConversionHasBeenCompleted,
    ConversionWillStart,
    MediaHasBeenAdded,
)
from arvel.media.exceptions import MediaValidationError
from arvel.media.image_processor import ImageProcessor, is_processable
from arvel.media.types import Media
from arvel.storage.config import StorageSettings
from arvel.storage.contracts import StorageContract  # noqa: TC001

if TYPE_CHECKING:
    from collections.abc import Callable

    from arvel.media.events import MediaEvent
    from arvel.media.types import (
        Conversion,
        JsonValue,
        MediaCollection,
        MediaOwnerOrDict,
    )

_MIME_TO_EXT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _extension_for_mime(mime: str) -> str:
    return _MIME_TO_EXT.get(mime, ".bin")


class MediaManager(MediaContract):
    """Store media files and model associations using configured storage."""

    def __init__(self, storage: StorageContract, settings: MediaSettings) -> None:
        self._storage = storage
        self._settings = settings
        self._default_disk = StorageSettings().driver
        self._processor = ImageProcessor(
            quality=settings.conversion_quality,
            output_format=settings.conversion_format,
        )
        self._items: list[Media] = []
        self._collections: dict[tuple[type, str], MediaCollection] = {}
        self._auto_registered: set[type] = set()
        self._next_id = 1
        self._event_listeners: list[Callable[[MediaEvent], None]] = []

    # ── Events ────────────────────────────────────────────────

    def on_event(self, listener: Callable[[MediaEvent], None]) -> None:
        self._event_listeners.append(listener)

    def _dispatch(self, event: MediaEvent) -> None:
        for listener in self._event_listeners:
            listener(event)

    # ── Registration ──────────────────────────────────────────

    def register_collection(self, model_type: type, collection: MediaCollection) -> None:
        self._collections[(model_type, collection.name)] = collection

    def get_registered_collections(self, model_type: type) -> list[MediaCollection]:
        return [col for (mt, _), col in self._collections.items() if mt is model_type]

    # ── Internal helpers ──────────────────────────────────────

    def _model_ref(self, model: MediaOwnerOrDict) -> tuple[str, int]:
        if isinstance(model, dict):
            return str(model.get("type", "")), int(model.get("id", 0))  # ty: ignore[no-matching-overload]
        return type(model).__name__, int(getattr(model, "id", 0))

    def _model_type_key(self, model: MediaOwnerOrDict) -> type:
        return type(model) if not isinstance(model, dict) else dict

    def _auto_register(self, model: MediaOwnerOrDict) -> None:
        """Auto-register collections from HasMedia.register_media_collections()."""
        if isinstance(model, dict):
            return
        model_type = type(model)
        if model_type in self._auto_registered:
            return
        self._auto_registered.add(model_type)
        register_fn = getattr(model, "register_media_collections", None)
        if callable(register_fn):
            for col in register_fn():
                self.register_collection(model_type, col)

    def _get_collection(
        self, model: MediaOwnerOrDict, collection_name: str
    ) -> MediaCollection | None:
        return self._collections.get((self._model_type_key(model), collection_name))

    def _disk_for_collection(self, model: MediaOwnerOrDict, collection_name: str) -> str:
        """Return the storage disk for a collection, falling back to the global default."""
        registered = self._get_collection(model, collection_name)
        if registered and registered.disk:
            return registered.disk
        return self._default_disk

    def _validate(
        self,
        model: MediaOwnerOrDict,
        file: bytes,
        collection: str,
        content_type: str | None,
    ) -> None:
        registered = self._get_collection(model, collection)
        if registered is None:
            return
        if registered.allowed_mime_types and content_type not in registered.allowed_mime_types:
            raise MediaValidationError(collection, f"MIME type '{content_type}' not allowed")
        if registered.max_file_size > 0 and len(file) > registered.max_file_size:
            raise MediaValidationError(
                collection,
                f"File size {len(file)} exceeds max {registered.max_file_size}",
            )
        if registered.accept_file and not registered.accept_file(file, collection, content_type):
            raise MediaValidationError(
                collection, "File rejected by collection's accept_file callback"
            )
        if content_type and is_processable(content_type) and registered.max_dimension > 0:
            self._validate_dimensions(file, registered.max_dimension, collection)

    def _validate_dimensions(self, file: bytes, max_dim: int, collection: str) -> None:
        try:
            import io

            from PIL import Image

            img = Image.open(io.BytesIO(file))
            w, h = img.size
            if w > max_dim or h > max_dim:
                raise MediaValidationError(
                    collection,
                    f"Image dimensions {w}x{h} exceed max_dimension {max_dim}",
                )
        except MediaValidationError:
            raise
        except Exception:  # noqa: S110 — non-image files silently pass validation
            pass

    async def _enforce_collection_limits(
        self, model: MediaOwnerOrDict, collection_name: str
    ) -> None:
        registered = self._get_collection(model, collection_name)
        if registered is None:
            return
        model_type, model_id = self._model_ref(model)
        items = [
            m
            for m in self._items
            if m.model_type == model_type
            and m.model_id == model_id
            and m.collection == collection_name
        ]
        items.sort(key=lambda m: m.order_column)

        limit = 0
        if registered.single_file:
            limit = 1
        elif registered.max_items > 0:
            limit = registered.max_items

        if limit > 0 and len(items) >= limit:
            to_remove = items[: len(items) - limit + 1]
            for old in to_remove:
                await self.delete_media(old)

    # ── Core API ──────────────────────────────────────────────

    async def add(
        self,
        model: MediaOwnerOrDict,
        file: bytes,
        filename: str,
        *,
        collection: str = "default",
        content_type: str | None = None,
        process: bool = True,
        custom_properties: dict[str, JsonValue] | None = None,
        name: str = "",
        order: int | None = None,
    ) -> Media:
        self._auto_register(model)
        self._validate(model, file, collection, content_type)
        await self._enforce_collection_limits(model, collection)

        model_type, model_id = self._model_ref(model)
        media_uuid = str(uuid.uuid4())
        generated_name = f"{media_uuid}-{filename}"
        base_dir = f"{self._settings.path_prefix}/{model_type}/{model_id}/{collection}"
        path = f"{base_dir}/{generated_name}"
        disk = self._disk_for_collection(model, collection)

        await self._storage.put(path, file, content_type=content_type)

        conversions: dict[str, str] = {}
        mime = content_type or "application/octet-stream"

        if process and is_processable(mime):
            registered = self._get_collection(model, collection)
            if registered and registered.conversions:
                applicable = [c for c in registered.conversions if c.should_apply_to(collection)]
                if applicable:
                    conversions = await self._run_conversions(
                        file, applicable, base_dir, generated_name, mime, media_ref=None
                    )

        media = Media(
            id=self._next_id,
            uuid=media_uuid,
            model_type=model_type,
            model_id=model_id,
            collection=collection,
            name=name or PurePosixPath(filename).stem,
            filename=generated_name,
            original_filename=filename,
            mime_type=mime,
            size=len(file),
            disk=disk,
            path=path,
            conversions=conversions,
            custom_properties=custom_properties or {},
            order_column=order if order is not None else self._next_id,
        )
        self._next_id += 1
        self._items.append(media)
        self._dispatch(MediaHasBeenAdded(media=media))
        return media

    async def _run_conversions(
        self,
        file: bytes,
        conversions: list[Conversion],
        base_dir: str,
        original_name: str,
        source_mime: str,
        *,
        media_ref: Media | None,
    ) -> dict[str, str]:
        results: dict[str, str] = {}
        stem = PurePosixPath(original_name).stem

        for conv in conversions:
            if media_ref:
                self._dispatch(ConversionWillStart(media=media_ref, conversion=conv))

            quality = conv.quality if conv.quality > 0 else self._settings.conversion_quality
            fmt = conv.format if conv.format != "source" else self._settings.conversion_format

            proc = ImageProcessor(quality=quality, output_format=fmt)
            processed, out_mime = proc.process(file, conv, source_mime=source_mime)
            ext = _extension_for_mime(out_mime)
            conv_name = f"{stem}-{conv.name}{ext}"
            conv_path = f"{base_dir}/conversions/{conv.name}/{conv_name}"
            await self._storage.put(conv_path, processed, content_type=out_mime)
            results[conv.name] = conv_path

            if media_ref:
                self._dispatch(ConversionHasBeenCompleted(media=media_ref, conversion=conv))

        return results

    # ── Retrieval ─────────────────────────────────────────────

    async def get_media(
        self,
        model: MediaOwnerOrDict,
        collection: str = "default",
        *,
        filters: dict[str, JsonValue] | Callable[[Media], bool] | None = None,
    ) -> list[Media]:
        self._auto_register(model)
        model_type, model_id = self._model_ref(model)
        items = [
            m
            for m in self._items
            if m.model_type == model_type and m.model_id == model_id and m.collection == collection
        ]
        if filters is not None:
            if callable(filters):
                items = [m for m in items if filters(m)]  # ty: ignore[call-top-callable]
            elif isinstance(filters, dict):
                items = [
                    m
                    for m in items
                    if all(m.get_custom_property(k) == v for k, v in filters.items())
                ]
        items.sort(key=lambda m: m.order_column)
        return items

    async def get_all_media(self, model: MediaOwnerOrDict) -> list[Media]:
        self._auto_register(model)
        model_type, model_id = self._model_ref(model)
        items = [m for m in self._items if m.model_type == model_type and m.model_id == model_id]
        items.sort(key=lambda m: m.order_column)
        return items

    async def get_first_media(
        self, model: MediaOwnerOrDict, collection: str = "default"
    ) -> Media | None:
        items = await self.get_media(model, collection)
        return items[0] if items else None

    async def get_last_media(
        self, model: MediaOwnerOrDict, collection: str = "default"
    ) -> Media | None:
        items = await self.get_media(model, collection)
        return items[-1] if items else None

    async def get_first_url(
        self,
        model: MediaOwnerOrDict,
        collection: str = "default",
        conversion: str | None = None,
    ) -> str | None:
        items = await self.get_media(model, collection)
        if not items:
            registered = self._get_collection(model, collection)
            if registered:
                if conversion and conversion in registered.fallback_urls:
                    return registered.fallback_urls[conversion]
                if registered.fallback_url:
                    return registered.fallback_url
            return None
        first = items[0]
        if conversion:
            return first.conversions.get(conversion)
        return await self._storage.url(first.path)

    # ── Deletion ──────────────────────────────────────────────

    async def delete_media(self, media: Media) -> None:
        await self._storage.delete(media.path)
        for conv_path in media.conversions.values():
            await self._storage.delete(conv_path)
        self._items = [m for m in self._items if m.id != media.id]

    async def delete_all(self, model: MediaOwnerOrDict, collection: str | None = None) -> int:
        self._auto_register(model)
        model_type, model_id = self._model_ref(model)
        targets = [
            m
            for m in self._items
            if m.model_type == model_type
            and m.model_id == model_id
            and (collection is None or m.collection == collection)
        ]

        if collection is None:
            targets = [m for m in targets if self._should_cascade(model, m.collection)]

        for media in targets:
            await self._storage.delete(media.path)
            for conv_path in media.conversions.values():
                await self._storage.delete(conv_path)

        removed_ids = {m.id for m in targets}
        before = len(self._items)
        self._items = [m for m in self._items if m.id not in removed_ids]
        count = before - len(self._items)

        if collection is not None:
            self._dispatch(
                CollectionHasBeenCleared(
                    model_type=model_type, model_id=model_id, collection_name=collection
                )
            )
        return count

    def _should_cascade(self, model: MediaOwnerOrDict, collection_name: str) -> bool:
        """Return True if items in *collection_name* should be deleted on cascade."""
        registered = self._get_collection(model, collection_name)
        if registered is None:
            return True
        return registered.cascade_delete

    async def clear_media_collection_except(
        self, model: MediaOwnerOrDict, collection: str, *, keep: list[int] | None = None
    ) -> int:
        self._auto_register(model)
        keep_ids = set(keep or [])
        model_type, model_id = self._model_ref(model)
        targets = [
            m
            for m in self._items
            if m.model_type == model_type
            and m.model_id == model_id
            and m.collection == collection
            and m.id not in keep_ids
        ]
        for media in targets:
            await self._storage.delete(media.path)
            for conv_path in media.conversions.values():
                await self._storage.delete(conv_path)

        removed_ids = {m.id for m in targets}
        before = len(self._items)
        self._items = [m for m in self._items if m.id not in removed_ids]
        return before - len(self._items)

    # ── Ordering ──────────────────────────────────────────────

    async def set_new_order(self, media_ids: list[int], start_order: int = 1) -> None:
        id_to_order = {mid: start_order + i for i, mid in enumerate(media_ids)}
        for m in self._items:
            if m.id in id_to_order:
                m.order_column = id_to_order[m.id]

    # ── Regeneration ──────────────────────────────────────────

    async def regenerate_conversions(
        self, model: MediaOwnerOrDict, collection: str = "default"
    ) -> list[Media]:
        items = await self.get_media(model, collection)
        registered = self._get_collection(model, collection)
        if not registered or not registered.conversions:
            return items

        updated: list[Media] = []
        for media in items:
            if not is_processable(media.mime_type):
                updated.append(media)
                continue

            for conv_path in media.conversions.values():
                await self._storage.delete(conv_path)

            file_bytes = await self._storage.get(media.path)
            if file_bytes is None:
                updated.append(media)
                continue

            model_type, model_id = self._model_ref(model)
            base_dir = f"{self._settings.path_prefix}/{model_type}/{model_id}/{collection}"
            applicable = [c for c in registered.conversions if c.should_apply_to(collection)]
            new_conversions = await self._run_conversions(
                file_bytes,
                applicable,
                base_dir,
                media.filename,
                media.mime_type,
                media_ref=media,
            )
            media.conversions = new_conversions
            updated.append(media)

        return updated
