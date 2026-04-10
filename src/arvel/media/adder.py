"""MediaAdder — fluent builder for attaching files to models.

Usage::

    await (
        model.add_media(file_bytes, "photo.jpg")
        .using_name("Profile photo")
        .using_file_name("profile.jpg")
        .with_custom_properties({"alt": "User avatar"})
        .to_media_collection("avatars")
    )
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from arvel.media.contracts import MediaContract
    from arvel.media.types import JsonValue, Media, MediaOwnerOrDict


class MediaAdder:
    """Fluent builder that collects options before storing a media item."""

    def __init__(
        self,
        contract: MediaContract,
        model: MediaOwnerOrDict,
        file: bytes,
        filename: str,
        *,
        content_type: str | None = None,
    ) -> None:
        self._contract = contract
        self._model = model
        self._file = file
        self._filename = filename
        self._content_type = content_type
        self._name: str = ""
        self._custom_name: str = ""
        self._custom_properties: dict[str, JsonValue] = {}
        self._process: bool = True
        self._preserving_original: bool = False
        self._order: int | None = None

    def using_name(self, name: str) -> Self:
        """Set the display name for this media item."""
        self._name = name
        return self

    def using_file_name(self, filename: str) -> Self:
        """Override the stored filename."""
        self._custom_name = filename
        return self

    def with_custom_properties(self, properties: dict[str, JsonValue]) -> Self:
        """Attach custom metadata properties to the media item."""
        self._custom_properties.update(properties)
        return self

    def preserving_original(self) -> Self:
        """Keep the original file on disk (future API for path/URL-based adds)."""
        self._preserving_original = True
        return self

    def with_order(self, order: int) -> Self:
        """Set the order_column value for this media item."""
        self._order = order
        return self

    def without_conversions(self) -> Self:
        """Skip conversion generation for this upload."""
        self._process = False
        return self

    async def to_media_collection(self, collection: str = "default") -> Media:
        """Store the file and associate it with the model in *collection*."""
        filename = self._custom_name or self._filename
        name = self._name or PurePosixPath(filename).stem

        media = await self._contract.add(
            self._model,
            self._file,
            filename,
            collection=collection,
            content_type=self._content_type,
            process=self._process,
            custom_properties=self._custom_properties,
            name=name,
            order=self._order,
        )
        return media
