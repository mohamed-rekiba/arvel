"""Shared test stubs for the e-commerce domain models.

``LocalMediaMixin`` — sync get_media / attach_media for unit-test compatibility.
``_MockMediaItem`` — in-memory media record returned by attach_media.

Real media uses ``arvel_image.HasMedia`` directly.
``TranslatableMixin`` is imported from ``arvel.database.mixins`` (framework).
"""

from __future__ import annotations

from typing import Any

from arvel.database import TranslatableMixin


class _MockMediaItem:
    """In-memory media record produced by ``LocalMediaMixin.attach_media``."""

    def __init__(
        self,
        *,
        collection_name: str,
        model_type: str,
        filename: str,
        content: bytes,
    ) -> None:
        self.collection_name = collection_name
        self.model_type = model_type
        self.filename = filename
        self.content = content


class LocalMediaMixin:
    """Sync get_media / attach_media for in-memory unit-test usage.


    Overrides arvel_image's async ``get_media`` with a sync version that
    operates on an in-process ``_local_media`` dict. Integration code uses
    ``add_media()`` from arvel_image directly for real file storage.
    """

    def get_media(self, collection: str = "default") -> list[_MockMediaItem]:
        store: dict[str, list[_MockMediaItem]] = getattr(self, "_local_media", {})
        return list(store.get(collection, []))

    def attach_media(self, file: Any, collection: str) -> _MockMediaItem:
        """Store ``file`` in the named collection and return a media record."""
        item = _MockMediaItem(
            collection_name=collection,
            model_type=type(self).__name__.lower(),
            filename=getattr(file, "filename", ""),
            content=getattr(file, "content", b""),
        )
        try:
            store: dict[str, list[_MockMediaItem]] = getattr(self, "_local_media", {})
            store.setdefault(collection, []).append(item)
            object.__setattr__(self, "_local_media", store)
        except AttributeError, TypeError:
            pass
        return item


class BaseModelMixin:
    """Mixin marker for domain models.


    Intentionally empty — framework ActiveRecord methods (delete, restore,
    scope_active) must not be shadowed by sync implementations here.
    """


__all__ = [
    "BaseModelMixin",
    "LocalMediaMixin",
    "TranslatableMixin",
    "_MockMediaItem",
]
