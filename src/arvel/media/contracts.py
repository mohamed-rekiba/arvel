"""Media library contract — ABC for model-associated file management.

Provides the same feature set as
`Spatie Laravel Media Library <https://spatie.be/docs/laravel-medialibrary/v11>`_:

- Fluent ``MediaAdder`` for attaching files
- Typed media collections with constraints (single file, max items, MIME allowlist)
- Image conversions with resize, compress, format conversion (via Pillow)
- Custom properties (dot-notation, filterable)
- Media ordering via ``order_column``
- Lifecycle events (added, conversion start/complete, collection cleared)
- Regeneration of conversions
- Fallback URLs when no media exists
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from arvel.media.events import MediaEvent
    from arvel.media.types import (
        JsonValue,
        Media,
        MediaCollection,
        MediaOwnerOrDict,
    )


class MediaContract(ABC):
    """Abstract base class for the media library.

    All ``model`` parameters accept ``MediaOwner`` (any object with ``id: int``)
    or ``MediaModelDict`` (``{"type": "...", "id": N}``) for testing convenience.
    """

    # ── Events ────────────────────────────────────────────────

    @abstractmethod
    def on_event(self, listener: Callable[[MediaEvent], None]) -> None:
        """Register a listener for media lifecycle events."""

    # ── Registration ──────────────────────────────────────────

    @abstractmethod
    def register_collection(self, model_type: type, collection: MediaCollection) -> None:
        """Register a media collection definition for a model type."""

    @abstractmethod
    def get_registered_collections(self, model_type: type) -> list[MediaCollection]:
        """Return all registered collections for *model_type*."""

    # ── Core API ──────────────────────────────────────────────

    @abstractmethod
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
        """Store *file* and associate with *model* in *collection*.

        Validates constraints, generates conversions, enforces single_file/max_items,
        dispatches ``MediaHasBeenAdded`` event.
        """

    # ── Retrieval ─────────────────────────────────────────────

    @abstractmethod
    async def get_media(
        self,
        model: MediaOwnerOrDict,
        collection: str = "default",
        *,
        filters: dict[str, JsonValue] | Callable[[Media], bool] | None = None,
    ) -> list[Media]:
        """Return all media in *collection*, optionally filtered."""

    @abstractmethod
    async def get_all_media(self, model: MediaOwnerOrDict) -> list[Media]:
        """Return all media across all collections for *model*."""

    @abstractmethod
    async def get_first_media(
        self, model: MediaOwnerOrDict, collection: str = "default"
    ) -> Media | None:
        """Return the first media item in *collection*, or None."""

    @abstractmethod
    async def get_last_media(
        self, model: MediaOwnerOrDict, collection: str = "default"
    ) -> Media | None:
        """Return the last media item in *collection*, or None."""

    @abstractmethod
    async def get_first_url(
        self,
        model: MediaOwnerOrDict,
        collection: str = "default",
        conversion: str | None = None,
    ) -> str | None:
        """Return the URL of the first media item, optionally for a specific conversion.

        Behavior when *conversion* is given but not found on the first item:
        returns ``None`` (does NOT fall back to the original file URL).

        Returns the collection's ``fallback_url`` (or ``fallback_urls[conversion]``)
        if no media exists at all.
        """

    # ── Deletion ──────────────────────────────────────────────

    @abstractmethod
    async def delete_media(self, media: Media) -> None:
        """Remove the media file (and all conversions) from storage and delete the record."""

    @abstractmethod
    async def delete_all(self, model: MediaOwnerOrDict, collection: str | None = None) -> int:
        """Remove all media for *model* (optionally filtered by collection).

        Respects ``cascade_delete=False`` on collections — items in non-cascading
        collections are skipped unless *collection* explicitly targets them.

        Return count deleted. Dispatches ``CollectionHasBeenCleared`` event.
        """

    @abstractmethod
    async def clear_media_collection_except(
        self,
        model: MediaOwnerOrDict,
        collection: str,
        *,
        keep: list[int] | None = None,
    ) -> int:
        """Remove all media in *collection* except items with IDs in *keep*."""

    # ── Ordering ──────────────────────────────────────────────

    @abstractmethod
    async def set_new_order(self, media_ids: list[int], start_order: int = 1) -> None:
        """Reorder media items by setting ``order_column`` in the given sequence."""

    # ── Regeneration ──────────────────────────────────────────

    @abstractmethod
    async def regenerate_conversions(
        self, model: MediaOwnerOrDict, collection: str = "default"
    ) -> list[Media]:
        """Re-process conversions for all media in *collection*. Returns updated media."""
