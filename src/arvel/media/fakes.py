"""MediaFake — in-memory testing double for the media library.

Implements the full ``MediaContract`` interface including event dispatch,
custom properties, ordering, single_file / max_items, cascade_delete,
max_dimension enforcement, and conversion simulation.

Behavioral parity with ``MediaManager``: every event that the manager
dispatches is also dispatched by the fake.
"""

from __future__ import annotations

import uuid
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from arvel.media.contracts import MediaContract
from arvel.media.events import (
    CollectionHasBeenCleared,
    ConversionHasBeenCompleted,
    ConversionWillStart,
    MediaHasBeenAdded,
)
from arvel.media.exceptions import MediaValidationError
from arvel.media.image_processor import is_processable
from arvel.media.types import Media

if TYPE_CHECKING:
    from collections.abc import Callable

    from arvel.media.events import MediaEvent
    from arvel.media.types import (
        JsonValue,
        MediaCollection,
        MediaOwnerOrDict,
    )


class MediaFake(MediaContract):
    """In-memory media library for tests with validation, events, and assertion helpers."""

    def __init__(self) -> None:
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

    def _get_collection(
        self, model: MediaOwnerOrDict, collection_name: str
    ) -> MediaCollection | None:
        return self._collections.get(
            (type(model) if not isinstance(model, dict) else dict, collection_name)
        )

    def _model_ref(self, model: MediaOwnerOrDict) -> tuple[str, int]:
        if isinstance(model, dict):
            return str(model.get("type", "")), int(model.get("id", 0))  # ty: ignore[no-matching-overload]
        return type(model).__name__, int(getattr(model, "id", 0))

    def _auto_register(self, model: MediaOwnerOrDict) -> None:
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

    def _validate(
        self, model: MediaOwnerOrDict, file: bytes, collection: str, content_type: str | None
    ) -> None:
        col = self._get_collection(model, collection)
        if col is None:
            return
        if col.allowed_mime_types and content_type not in col.allowed_mime_types:
            raise MediaValidationError(collection, f"MIME type '{content_type}' not allowed")
        if col.max_file_size > 0 and len(file) > col.max_file_size:
            raise MediaValidationError(
                collection, f"File size {len(file)} exceeds max {col.max_file_size}"
            )
        if col.accept_file and not col.accept_file(file, collection, content_type):
            raise MediaValidationError(collection, "File rejected by accept_file callback")
        if content_type and is_processable(content_type) and col.max_dimension > 0:
            self._validate_dimensions(file, col.max_dimension, collection)

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

    def _should_cascade(self, model: MediaOwnerOrDict, collection_name: str) -> bool:
        registered = self._get_collection(model, collection_name)
        if registered is None:
            return True
        return registered.cascade_delete

    async def _enforce_limits(self, model: MediaOwnerOrDict, collection_name: str) -> None:
        model_type, model_id = self._model_ref(model)
        items = [
            m
            for m in self._items
            if m.model_type == model_type
            and m.model_id == model_id
            and m.collection == collection_name
        ]
        items.sort(key=lambda m: m.order_column)
        col = self._get_collection(model, collection_name)
        if col is None:
            return
        limit = 1 if col.single_file else (col.max_items if col.max_items > 0 else 0)
        if limit > 0 and len(items) >= limit:
            for old in items[: len(items) - limit + 1]:
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
        await self._enforce_limits(model, collection)

        gen_uuid = str(uuid.uuid4())
        gen_name = f"{gen_uuid}-{filename}"
        fake_path = f"fake/{collection}/{gen_name}"

        conversions: dict[str, str] = {}
        if process:
            col = self._get_collection(model, collection)
            if col and col.conversions:
                for conv in col.conversions:
                    if conv.should_apply_to(collection):
                        conversions[conv.name] = f"{fake_path}/conversions/{conv.name}/{gen_name}"

        model_type, model_id = self._model_ref(model)
        media = Media(
            id=self._next_id,
            uuid=gen_uuid,
            model_type=model_type,
            model_id=model_id,
            collection=collection,
            name=name or PurePosixPath(filename).stem,
            filename=gen_name,
            original_filename=filename,
            mime_type=content_type or "application/octet-stream",
            size=len(file),
            disk="fake",
            path=fake_path,
            conversions=conversions,
            custom_properties=custom_properties or {},
            order_column=order if order is not None else self._next_id,
        )
        self._next_id += 1
        self._items.append(media)
        self._dispatch(MediaHasBeenAdded(media=media))
        return media

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
            col = self._get_collection(model, collection)
            if col:
                if conversion and conversion in col.fallback_urls:
                    return col.fallback_urls[conversion]
                if col.fallback_url:
                    return col.fallback_url
            return None
        first = items[0]
        if conversion:
            return first.conversions.get(conversion)
        return f"/fake-storage/{first.path}"

    # ── Deletion ──────────────────────────────────────────────

    async def delete_media(self, media: Media) -> None:
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

    async def clear_media_collection_except(
        self, model: MediaOwnerOrDict, collection: str, *, keep: list[int] | None = None
    ) -> int:
        self._auto_register(model)
        keep_ids = set(keep or [])
        model_type, model_id = self._model_ref(model)
        before = len(self._items)
        self._items = [
            m
            for m in self._items
            if not (
                m.model_type == model_type
                and m.model_id == model_id
                and m.collection == collection
                and m.id not in keep_ids
            )
        ]
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
        col = self._get_collection(model, collection)
        if not col or not col.conversions:
            return items
        for media in items:
            for conv in col.conversions:
                if conv.should_apply_to(collection):
                    self._dispatch(ConversionWillStart(media=media, conversion=conv))
                    media.conversions[conv.name] = (
                        f"{media.path}/conversions/{conv.name}/{media.filename}"
                    )
                    self._dispatch(ConversionHasBeenCompleted(media=media, conversion=conv))
        return items

    # ── Test assertions ───────────────────────────────────────

    def assert_added(self, collection: str = "default") -> None:
        matches = [m for m in self._items if m.collection == collection]
        if not matches:
            msg = f"Expected media added to collection '{collection}', but none found"
            raise AssertionError(msg)

    def assert_nothing_added(self) -> None:
        if self._items:
            msg = f"Expected no media added, but got {len(self._items)}"
            raise AssertionError(msg)

    def assert_added_count(self, expected: int) -> None:
        actual = len(self._items)
        if actual != expected:
            msg = f"Expected {expected} media items, but got {actual}"
            raise AssertionError(msg)
