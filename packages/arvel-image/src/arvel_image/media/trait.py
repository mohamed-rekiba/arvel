"""``HasMedia`` mixin — gives any host model the polymorphic media API.

Hosts opt in by inheriting :class:`HasMedia` and (optionally) overriding
:meth:`register_media_collections`. The mixin provides:

- ``self.media`` — :class:`MorphMany[Media]` accessor (all collections).
- ``await self.add_media(bytes, file_name=...)`` — returns a
  :class:`FileAdder`; terminate with ``.to_media_collection(name)``.
- ``await self.add_media_from_url(url)`` — download + ingest with SSRF guard.
- ``await self.add_media_from_base64(data, file_name)`` — decode + ingest.
- ``await self.get_media(name)`` — ordered list of :class:`Media` rows.
- ``await self.get_media_url(name, conversion=None, fallback=None)`` — URL.
- ``await self.clear_media_collection(name)`` — delete every media + file.
"""

from __future__ import annotations

import base64 as _base64
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO, ClassVar, TypeGuard, Union

from arvel.database.orm.morph import MorphMany
from sqlalchemy import asc, nullslast

from arvel_image.media.exceptions import MediaError
from arvel_image.media.model import Media

if TYPE_CHECKING:
    from arvel_image.media.collection import MediaCollection
    from arvel_image.media.file_adder import FileAdder

# A media source — caller supplies any of these and ``add_media`` reduces
# them to ``bytes`` before handing off to :class:`FileAdder`.
MediaSource = Union[str, "os.PathLike[str]", bytes, bytearray, memoryview, BinaryIO]

_DATA_URI_RE = re.compile(r"^data:[^;]+;base64,", re.IGNORECASE)

# Default maximum download size for URL and base64 ingestion (10 MB).
_DEFAULT_MAX_BYTES = 10 * 1024 * 1024


def _read_from_file_like(source: object, file_name: str | None) -> tuple[bytes, str]:
    """Drain a file-like object (.read()) into bytes, requiring ``file_name``."""
    if not file_name:
        msg = "file_name is required when source is a file-like object"
        raise MediaError(msg)
    read = getattr(source, "read")  # noqa: B009
    data: object = read()
    if isinstance(data, str):
        data = data.encode()
    if isinstance(data, bytes):
        return data, file_name
    if isinstance(data, bytearray):
        return bytes(data), file_name
    if isinstance(data, memoryview):
        return data.tobytes(), file_name
    msg = f"file-like object must return bytes from read(); got {type(data).__name__}"
    raise MediaError(msg)


def _coerce_source(source: MediaSource, file_name: str | None) -> tuple[bytes, str]:
    """Reduce ``source`` to ``(contents, file_name)``."""
    if isinstance(source, (bytes, bytearray, memoryview)):
        if not file_name:
            msg = "file_name is required when source is bytes-like"
            raise MediaError(msg)
        return bytes(source), file_name

    if isinstance(source, (str, os.PathLike)):
        path = Path(os.fspath(source))
        try:
            contents = path.read_bytes()
        except OSError as exc:
            msg = f"Could not read media from {path}: {exc}"
            raise MediaError(msg) from exc
        return contents, file_name or path.name

    if callable(getattr(source, "read", None)):
        return _read_from_file_like(source, file_name)

    msg = f"Unsupported media source type: {type(source).__name__}"
    raise MediaError(msg)


def _model_type_for(host: HasMedia) -> str:
    """Return the model_type string used to look up Media rows for ``host``.

    Checks for a ``__media_host_type__`` class attribute first so that view
    models (e.g. ``PublishedProduct``) can transparently reuse the Media rows
    stored under the canonical mutable model name (e.g. ``"Product"``).
    """
    return getattr(type(host), "__media_host_type__", None) or type(host).__name__


async def get_media_ordered(host: HasMedia, collection: str) -> list[Media]:
    """Return Media rows for ``host`` in ``collection`` ordered by order_column, id.

    Public helper — used by :class:`FileAdder` and :meth:`HasMedia.get_media`
    (FR-046-04, FR-050-29).
    """
    query = (
        Media.query()
        .where(Media.model_type == _model_type_for(host))
        .where(Media.model_id == str(host.host_pk()))
        .where(Media.collection_name == collection)
        .order_by(nullslast(asc(Media.order_column)), asc(Media.id))
    )
    return list(await query.all())


def _apply_dict_filters(rows: list[Media], criteria: dict[str, Any]) -> list[Media]:
    return [m for m in rows if all(m.custom_properties.get(k) == v for k, v in criteria.items())]


def _is_dict_filter(
    v: dict[str, Any] | Callable[[Media], bool] | None,
) -> TypeGuard[dict[str, Any]]:
    return isinstance(v, dict)


class HasMedia:
    """Mixin providing a polymorphic ``media`` collection on any host model."""

    media: ClassVar[MorphMany[Media]] = MorphMany(Media, name="model")

    __arvel_media_collections__: ClassVar[dict[str, Any]] = {}
    __arvel_collections_registered__: ClassVar[bool] = False

    # ─── overridable hook ──────────────────────────────────────────────────

    def register_media_collections(self) -> None:
        """Subclasses override to declare collections via
        :class:`MediaCollection.register_on`. Called once per host class.
        """

    # ─── public surface ────────────────────────────────────────────────────

    def add_media(self, source: MediaSource, *, file_name: str | None = None) -> FileAdder:
        """Begin ingestion of ``source`` (FR-026-11)."""
        from arvel_image.media.file_adder import FileAdder  # noqa: PLC0415

        contents, resolved_name = _coerce_source(source, file_name)
        return FileAdder(self, contents, file_name=resolved_name)

    async def add_media_from_url(
        self,
        url: str,
        *,
        file_name: str | None = None,
        max_bytes: int = _DEFAULT_MAX_BYTES,
    ) -> FileAdder:
        """Download ``url`` and return a :class:`FileAdder` (FR-046-05).

        The SSRF guard rejects RFC-1918, loopback, and link-local addresses.
        Only http/https schemes are permitted (FR-050-11).
        DNS rebinding is a known limitation (ADR-109).
        """
        from arvel_image.media.file_adder import FileAdder  # noqa: PLC0415
        from arvel_image.media.url_fetcher import fetch_url  # noqa: PLC0415

        contents, derived_name = await fetch_url(url, max_bytes=max_bytes)
        resolved_name = FileAdder.sanitize_file_name(file_name or derived_name)
        return FileAdder(self, contents, file_name=resolved_name)

    async def add_media_from_base64(
        self,
        data: str,
        file_name: str,
        *,
        max_bytes: int = _DEFAULT_MAX_BYTES,
    ) -> FileAdder:
        """Decode a base64 string and return a :class:`FileAdder` (FR-046-11).

        Strips ``data:<mime>;base64,`` prefix before decoding.
        """
        from arvel_image.media.file_adder import FileAdder  # noqa: PLC0415

        raw = _DATA_URI_RE.sub("", data)
        try:
            contents = _base64.b64decode(raw, validate=True)
        except Exception as exc:
            msg = f"Invalid base64 data: {exc}"
            raise MediaError(msg) from exc

        if len(contents) > max_bytes:
            msg = f"Decoded base64 exceeds max_bytes={max_bytes}"
            raise MediaError(msg)

        resolved_name = FileAdder.sanitize_file_name(file_name)
        return FileAdder(self, contents, file_name=resolved_name)

    async def add_media_from_disk(
        self,
        path: str,
        *,
        disk: str = "default",
    ) -> FileAdder:
        """Read a file from a storage disk and return a :class:`FileAdder` (FR-050-22).

        Reads via the Storage facade so disk-level access controls apply.
        """
        from arvel.facades.storage import Storage  # noqa: PLC0415

        from arvel_image.media.file_adder import FileAdder  # noqa: PLC0415

        disk_target: str | None = None if disk == "default" else disk
        storage_disk = Storage.disk(disk_target)
        contents = await storage_disk.get(path)
        file_name = path.rsplit("/", maxsplit=1)[-1] or "file"
        return FileAdder(self, contents, file_name=file_name)

    def add_media_from_string(
        self,
        content: str | bytes,
        *,
        file_name: str = "text.txt",
    ) -> FileAdder:
        """Wrap a string/bytes payload and return a :class:`FileAdder` (FR-050-23).

        Default ``file_name`` is ``"text.txt"``; override via ``.using_file_name()``.
        """
        from arvel_image.media.file_adder import FileAdder  # noqa: PLC0415

        raw = content.encode() if isinstance(content, str) else bytes(content)
        return FileAdder(self, raw, file_name=file_name)

    async def get_media(
        self,
        collection: str = "default",
        *,
        filters: dict[str, Any] | Callable[[Media], bool] | None = None,
    ) -> list[Media]:
        """Return every :class:`Media` row in ``collection`` ordered by order_column, id.

        ``"*"`` returns all rows across all collections (FR-050-27).
        ``filters`` applies Python-side filtering (FR-050-17).
        """
        if collection == "*":
            rows = await self._get_all_media()
        else:
            rows = await get_media_ordered(self, collection)

        if filters is None:
            return rows

        if _is_dict_filter(filters):
            return _apply_dict_filters(rows, filters)
        if callable(filters):
            return [m for m in rows if filters(m)]
        return rows  # unreachable — filters is never None here (handled above)

    async def _get_all_media(self) -> list[Media]:
        """Fetch all Media rows for this host across all collections (FR-050-27)."""
        query = (
            Media.query()
            .where(Media.model_type == _model_type_for(self))
            .where(Media.model_id == str(self.host_pk()))
            .order_by(nullslast(asc(Media.order_column)), asc(Media.id))
        )
        return list(await query.all())

    async def get_first_media(self, collection: str = "default") -> Media | None:
        """Return the first :class:`Media` in ``collection``, or ``None``."""
        rows = await get_media_ordered(self, collection)
        return rows[0] if rows else None

    async def get_last_media(self, collection: str = "default") -> Media | None:
        """Return the :class:`Media` with the highest order_column in ``collection`` (FR-050-12)."""
        rows = await get_media_ordered(self, collection)
        return rows[-1] if rows else None

    async def get_media_url(
        self,
        collection: str = "default",
        conversion: str | None = None,
        fallback: str | None = None,
    ) -> str | None:
        """Return the URL of the first media in ``collection``.

        Returns ``fallback`` when the collection is empty (FR-046-10).
        Falls back to collection-level fallback URL when no call-site fallback
        supplied and collection is configured with one (FR-050-15).
        """
        first = await self.get_first_media(collection)
        if first is not None:
            return await first.get_url(conversion)

        # Call-site fallback takes precedence over collection fallback.
        if fallback is not None:
            return fallback

        # FR-050-15: collection-level fallback.
        try:
            coll = self.collection_for(collection)
            return coll.get_fallback_url(conversion)
        except Exception:  # noqa: BLE001
            return None

    async def get_first_media_url(
        self,
        collection: str = "default",
        conversion: str | None = None,
        fallback: str | None = None,
    ) -> str | None:
        """Alias for :meth:`get_media_url` (FR-046-10)."""
        return await self.get_media_url(collection, conversion=conversion, fallback=fallback)

    async def get_last_media_url(
        self,
        collection: str = "default",
        conversion: str | None = None,
    ) -> str | None:
        """Return the URL of the last media in ``collection`` (FR-050-12)."""
        last = await self.get_last_media(collection)
        if last is None:
            return None
        return await last.get_url(conversion)

    async def clear_media_collection(self, collection: str = "default") -> int:
        """Delete every media + file in ``collection``. Returns the row count."""
        rows = await get_media_ordered(self, collection)
        for media in rows:
            await media.delete()
        return len(rows)

    async def clear_media_collection_except(
        self,
        collection: str,
        kept: Media | list[Media],
    ) -> int:
        """Delete every media in ``collection`` except ``kept`` (FR-050-13)."""
        kept_list = [kept] if isinstance(kept, Media) else list(kept)
        kept_ids = {m.id for m in kept_list}
        rows = await get_media_ordered(self, collection)
        deleted = 0
        for media in rows:
            if media.id not in kept_ids:
                await media.delete()
                deleted += 1
        return deleted

    async def attach_media(
        self,
        source: MediaSource,
        *,
        file_name: str | None = None,
        collection: str = "default",
    ) -> Media:
        """Ingest ``source`` and persist it to ``collection`` in one call."""
        return await self.add_media(source, file_name=file_name).to_media_collection(collection)

    async def delete_media(self, collection: str = "default") -> int:
        """Alias for ``clear_media_collection``."""
        return await self.clear_media_collection(collection)

    async def delete_preserving_media(self) -> Any:
        """Delete the host row without cascading to Media rows or files (FR-050-26)."""
        return await super().delete()  # type: ignore[misc]

    def get_registered_media_collections(self) -> list[MediaCollection]:
        """Return all declared MediaCollection objects (FR-050-14)."""
        self.ensure_collections()
        cls = type(self)
        registry: dict[str, MediaCollection] = cls.__dict__.get("__arvel_media_collections__") or {}
        return list(registry.values())

    # ─── package-internal helpers ──────────────────────────────────────────

    def collection_for(self, name: str) -> MediaCollection:
        """Resolve a :class:`MediaCollection` by name, registering on first use."""
        from arvel_image.media.collection import MediaCollection  # noqa: PLC0415
        from arvel_image.media.exceptions import UnknownCollectionError  # noqa: PLC0415

        self.ensure_collections()
        cls = type(self)
        registry: dict[str, MediaCollection] = cls.__dict__.get("__arvel_media_collections__") or {}
        if name in registry:
            return registry[name]
        if registry:
            msg = (
                f"Unknown media collection {name!r} on {cls.__name__}; "
                f"declared collections: {sorted(registry)}"
            )
            raise UnknownCollectionError(msg)
        return MediaCollection(name)

    def ensure_collections(self) -> None:
        """Call ``register_media_collections`` once per host class."""
        cls = type(self)
        if cls.__dict__.get("__arvel_collections_registered__"):
            return
        cls.__arvel_media_collections__ = {}
        self.register_media_collections()
        cls.__arvel_collections_registered__ = True

    def host_pk(self) -> Any:
        """Return this host's primary key as a string (FR-046-08)."""
        return str(self.id)  # type: ignore[attr-defined]


__all__ = ["HasMedia", "get_media_ordered"]
