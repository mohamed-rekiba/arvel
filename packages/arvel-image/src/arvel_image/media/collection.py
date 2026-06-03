"""Declarative media collection (a host's named bucket of media files)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from arvel_image.media.conversion import Conversion
    from arvel_image.media.trait import HasMedia


class FileInfo:
    """Lightweight descriptor passed to accepts_file callbacks"""

    __slots__ = ("file_name", "mime_type")

    def __init__(self, file_name: str, mime_type: str) -> None:
        self.file_name = file_name
        self.mime_type = mime_type


class MediaCollection:
    """Named bucket of media on a host model.

    - ``single_file=True`` → adding a new file deletes every previously-stored
      media in the collection (Spatie's ``singleFile()``).
    - ``disk`` → override the storage disk for originals in this collection.
    - ``conversions_disk`` → separate disk for conversion derivatives.
    - ``accept_mime_types([...])`` → reject files with non-matching MIME.
    - ``max_file_size(N)`` → reject files exceeding N bytes.
    - ``only_keep_latest(N)`` → prune oldest rows so at most N remain.
    - ``use_fallback_url(url, conversion=None)`` → default URL when empty
    - ``accepts_file(callback)`` → custom file acceptance callback
    """

    def __init__(
        self,
        name: str,
        *,
        single_file: bool = False,
        disk: str | None = None,
    ) -> None:
        if not name:
            msg = "MediaCollection name must be a non-empty string"
            raise ValueError(msg)
        self.name = name
        self.single_file = single_file
        self.disk = disk
        self.conversions: list[Conversion] = []
        self.conversions_disk: str | None = None
        self.accept_mime_types_list: list[str] | None = None
        self.max_file_size_bytes: int | None = None
        self.keep_latest_n: int | None = None
        self.responsive_images_enabled: bool = False
        # per-collection fallback URLs
        self._fallback_url: str | None = None
        self._fallback_urls: dict[str, str] = {}
        # custom file acceptance callback
        self._accepts_file_callback: Callable[[FileInfo], bool] | None = None

    def with_conversions(self, *conversions: Conversion) -> Self:
        """Append conversions that should run for every file added here."""
        self.conversions.extend(conversions)
        return self

    def use_disk(self, name: str) -> Self:
        """Override the storage disk for originals in this collection."""
        self.disk = name
        return self

    def use_conversions_disk(self, disk_name: str) -> Self:
        """Store conversion derivatives on a separate disk"""
        self.conversions_disk = disk_name
        return self

    def accept_mime_types(self, types: list[str]) -> Self:
        """Restrict ingestion to the supplied MIME types"""
        self.accept_mime_types_list = [t.lower() for t in types]
        return self

    def max_file_size(self, bytes_: int) -> Self:
        """Reject files larger than ``bytes_``"""
        self.max_file_size_bytes = bytes_
        return self

    def only_keep_latest(self, n: int) -> Self:
        """Prune to the most-recent ``n`` files after each add

        Mutually exclusive with ``single_file=True``.
        """
        if self.single_file:
            msg = "only_keep_latest and single_file are mutually exclusive"
            raise ValueError(msg)
        self.keep_latest_n = n
        return self

    def use_fallback_url(self, url: str, conversion: str | None = None) -> Self:
        """Set a fallback URL returned when the collection is empty

        ``conversion`` scopes the fallback to a specific conversion name.
        Call-site ``fallback=`` parameter takes precedence over this.
        """
        if conversion:
            self._fallback_urls[conversion] = url
        else:
            self._fallback_url = url
        return self

    def generate_responsive_images(self) -> Self:
        """Generate responsive width variants for every file added to this collection."""
        self.responsive_images_enabled = True
        return self

    def accepts_file(self, callback: Callable[[FileInfo], bool]) -> Self:
        """Register a callable that accepts or rejects each incoming file

        Receives a :class:`FileInfo` with ``.file_name`` and ``.mime_type``.
        Raises :class:`InvalidMimeTypeError` when callback returns ``False``.
        Compatible with ``accept_mime_types``; both must pass.
        """
        self._accepts_file_callback = callback
        return self

    def check_accepts_file(self, file_info: FileInfo) -> bool:
        """Return ``True`` if the callback accepts the file (or no callback is set)."""
        if self._accepts_file_callback is None:
            return True
        return self._accepts_file_callback(file_info)

    def get_fallback_url(self, conversion: str | None = None) -> str | None:
        """Resolve the fallback URL for the given conversion (or base fallback)."""
        if conversion and conversion in self._fallback_urls:
            return self._fallback_urls[conversion]
        return self._fallback_url

    def register_on(self, host: HasMedia) -> Self:
        """Store this collection on ``type(host)`` so :class:`HasMedia`
        can look it up by name.
        """
        cls: type[HasMedia] = type(host)
        registry: dict[str, MediaCollection] | None = cls.__dict__.get(
            "__arvel_media_collections__"
        )
        if registry is None:
            registry = {}
            cls.__arvel_media_collections__ = registry
        registry[self.name] = self
        return self


__all__ = ["FileInfo", "MediaCollection"]
