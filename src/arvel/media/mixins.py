"""HasMedia mixin — adds Spatie-style media helpers to any model.

Usage::

    class User(ArvelModel, HasMedia):
        __tablename__ = "users"

        def register_media_collections(self) -> list[MediaCollection]:
            return [
                MediaCollection(
                    name="avatars",
                    single_file=True,
                    allowed_mime_types=["image/jpeg", "image/png"],
                    max_file_size=5 * 1024 * 1024,
                    fallback_url="/images/anonymous-user.jpg",
                    conversions=[
                        Conversion(name="thumb", width=150, height=150),
                        Conversion(name="preview", width=300, height=300, fit="contain"),
                    ],
                ),
            ]

    # Fluent API
    media = await (
        user.add_media(file, "photo.jpg", content_type="image/jpeg")
        .using_name("Profile photo")
        .with_custom_properties({"alt": "avatar"})
        .to_media_collection("avatars")
    )

    # Quick API
    url = await user.first_media_url("avatars", conversion="thumb")

Naming conventions
------------------
The mixin uses "model-centric" names that read naturally on model instances:

- ``first_media_url()`` wraps ``MediaContract.get_first_url()``
- ``clear_media()`` wraps ``MediaContract.delete_all()``

Collections declared in ``register_media_collections()`` are auto-registered
with the contract on first media operation — no manual ``register_collection()``
call needed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.media.adder import MediaAdder

if TYPE_CHECKING:
    from collections.abc import Callable

    from arvel.media.contracts import MediaContract
    from arvel.media.types import JsonValue, Media, MediaCollection


class HasMedia:
    """Mixin that adds media attachment helpers to a model.

    Models using this mixin must have ``id`` and ``_media_contract`` attributes.
    Override ``register_media_collections()`` to declare collection constraints.

    Collections are auto-registered with the contract on first media operation.
    """

    id: int
    _media_contract: MediaContract

    def register_media_collections(self) -> list[MediaCollection]:
        """Override to declare media collections and their constraints.

        Returns an empty list by default — no collections registered.
        Called automatically on first media operation via the contract's
        auto-registration mechanism.
        """
        return []

    def get_registered_media_collections(self) -> list[MediaCollection]:
        """Return all registered media collections for this model type."""
        return self._media_contract.get_registered_collections(type(self))

    # ── Fluent adder ──────────────────────────────────────────

    def add_media(
        self,
        file: bytes,
        filename: str,
        *,
        content_type: str | None = None,
    ) -> MediaAdder:
        """Start a fluent media attachment. Chain methods, then call ``.to_media_collection()``."""
        return MediaAdder(
            self._media_contract,
            self,
            file,
            filename,
            content_type=content_type,
        )

    # ── Retrieval ─────────────────────────────────────────────

    async def media(
        self,
        collection: str = "default",
        *,
        filters: dict[str, JsonValue] | Callable[[Media], bool] | None = None,
    ) -> list[Media]:
        """Get all media items for this model in the given collection."""
        return await self._media_contract.get_media(self, collection, filters=filters)

    async def all_media(self) -> list[Media]:
        """Get all media across all collections."""
        return await self._media_contract.get_all_media(self)

    async def first_media(self, collection: str = "default") -> Media | None:
        """Get the first media item in the collection."""
        return await self._media_contract.get_first_media(self, collection)

    async def last_media(self, collection: str = "default") -> Media | None:
        """Get the last media item in the collection."""
        return await self._media_contract.get_last_media(self, collection)

    async def first_media_url(
        self,
        collection: str = "default",
        conversion: str | None = None,
    ) -> str | None:
        """Get the URL of the first media item, optionally for a conversion.

        Model-centric alias for ``MediaContract.get_first_url()``.
        Returns the collection's ``fallback_url`` if no media exists.
        Returns ``None`` if *conversion* is specified but not found on the item.
        """
        return await self._media_contract.get_first_url(self, collection, conversion)

    # ── Deletion ──────────────────────────────────────────────

    async def clear_media(self, collection: str | None = None) -> int:
        """Remove all media for this model, optionally filtered by collection.

        Model-centric alias for ``MediaContract.delete_all()``.
        Respects ``cascade_delete=False`` on collections.
        """
        return await self._media_contract.delete_all(self, collection)

    async def clear_media_collection_except(
        self, collection: str, *, keep: list[int] | None = None
    ) -> int:
        """Remove all media in *collection* except items with IDs in *keep*."""
        return await self._media_contract.clear_media_collection_except(self, collection, keep=keep)
