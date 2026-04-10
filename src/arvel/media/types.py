"""Media types — data structures, protocols, and type aliases for the media library."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, TypedDict, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable

# ── JSON value type ──────────────────────────────────────────
# Recursive type for JSON-safe values stored in custom_properties.

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


# ── Model owner protocol ────────────────────────────────────
# Every model that can own media must satisfy this protocol.


@runtime_checkable
class MediaOwner(Protocol):
    """Structural type for any object that can own media items.

    Satisfied by ``ArvelModel`` subclasses and any class with an ``id`` attribute.
    """

    id: int


class MediaModelDict(TypedDict):
    """Dict-based model stub for lightweight testing without ORM models."""

    type: str
    id: int


MediaOwnerOrDict = MediaOwner | MediaModelDict | dict[str, Any]
"""Union accepted by all media contract methods as the *model* parameter.

Use ``MediaOwner`` (any object with ``id: int``) for real models.
Use ``MediaModelDict`` (``{"type": "User", "id": 1}``) for tests.
``dict[str, Any]`` is accepted for pragmatic compatibility with dict literals
that type checkers infer as ``dict[str, str | int]`` instead of ``MediaModelDict``.
"""


# ── Conversion ───────────────────────────────────────────────


@dataclass
class Conversion:
    """An image conversion definition (e.g., thumbnail, banner).

    Mirrors Spatie's ``addMediaConversion()`` fluent API as a declarative dataclass.
    """

    name: str
    width: int = 0
    height: int = 0
    fit: str = "cover"
    format: str = "source"
    quality: int = 0
    sharpen: int = 0
    collections: list[str] = field(default_factory=list)

    def should_apply_to(self, collection_name: str) -> bool:
        """Return True if this conversion should run on *collection_name*."""
        if not self.collections:
            return True
        return collection_name in self.collections


# ── Media collection ─────────────────────────────────────────


@dataclass
class MediaCollection:
    """Configuration for a media collection on a model.

    Mirrors Spatie's ``registerMediaCollections`` builder pattern.

    Fields:
        disk: Storage disk name. When non-empty, files in this collection
            are stored on this disk instead of the global default.
        cascade_delete: When ``False``, items in this collection are
            skipped during ``delete_all()`` calls on the parent model.
        max_dimension: Maximum width/height in pixels. Images exceeding
            this on either axis are rejected with ``MediaValidationError``.
    """

    name: str
    allowed_mime_types: list[str] = field(default_factory=list)
    max_file_size: int = 0
    max_dimension: int = 10000
    conversions: list[Conversion] = field(default_factory=list)
    cascade_delete: bool = True
    single_file: bool = False
    max_items: int = 0
    disk: str = ""
    fallback_url: str = ""
    fallback_path: str = ""
    fallback_urls: dict[str, str] = field(default_factory=dict)
    accept_file: Callable[[bytes, str, str | None], bool] | None = None


# ── Media item ───────────────────────────────────────────────


@dataclass
class Media:
    """A media item associated with a model.

    In the full implementation, this is backed by the ``MediaItem`` ORM model.
    This dataclass defines the public shape for contract consumers.
    """

    id: int | None = None
    uuid: str = ""
    model_type: str = ""
    model_id: int = 0
    collection: str = "default"
    name: str = ""
    filename: str = ""
    original_filename: str = ""
    mime_type: str = ""
    size: int = 0
    disk: str = ""
    path: str = ""
    conversions: dict[str, str] = field(default_factory=dict)
    custom_properties: dict[str, JsonValue] = field(default_factory=dict)
    order_column: int = 0

    @property
    def human_readable_size(self) -> str:
        """Return file size in human-readable format (e.g. ``1.5 MB``)."""
        if self.size == 0:
            return "0 B"
        units = ("B", "KB", "MB", "GB", "TB")
        i = math.floor(math.log(self.size, 1024))
        i = min(i, len(units) - 1)
        val = self.size / (1024**i)
        return f"{val:.1f} {units[i]}" if i > 0 else f"{self.size} B"

    def has_custom_property(self, key: str) -> bool:
        """Check for a custom property, supporting dot notation."""
        return _dot_get(self.custom_properties, key, _SENTINEL) is not _SENTINEL

    def get_custom_property(self, key: str, default: JsonValue = None) -> JsonValue:
        """Get a custom property value, supporting dot notation."""
        return _dot_get(self.custom_properties, key, default)

    def set_custom_property(self, key: str, value: JsonValue) -> None:
        """Set a custom property, supporting dot notation."""
        _dot_set(self.custom_properties, key, value)

    def forget_custom_property(self, key: str) -> None:
        """Remove a custom property, supporting dot notation."""
        _dot_forget(self.custom_properties, key)


_SENTINEL = object()


def _dot_get(data: dict[str, Any], key: str, default: Any) -> Any:
    parts = key.split(".")
    current: Any = data
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def _dot_set(data: dict[str, Any], key: str, value: Any) -> None:
    parts = key.split(".")
    current = data
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def _dot_forget(data: dict[str, Any], key: str) -> None:
    parts = key.split(".")
    current = data
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return
        current = current[part]
    if isinstance(current, dict):
        current.pop(parts[-1], None)
