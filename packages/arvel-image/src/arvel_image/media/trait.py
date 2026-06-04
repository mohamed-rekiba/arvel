"""``HasMedia`` mixin — gives any model the polymorphic ``media`` collection.

DX-first API. One model, one collection, one upload call:

    class Product(HasMedia, Model):
        __media_collection__ = "images"

    # read (eager-loaded)
    product = await Product.with_("media").first()
    for image in product.media:
        print(image.url())

    # write — works with bytes, paths, URLs, base64, or file-like
    media = await product.add_image(file.read(), file_name="hero.jpg")
    media = await product.add_image("/tmp/photo.jpg")
    media = await product.add_image("https://example.com/img.png")
    media = await product.add_image("data:image/png;base64,iVBOR...")

    # serialize — to_dict() auto-appends serialized media when eager-loaded
    return product.to_dict()
    # {"id": ..., "media": [{"url": ..., "conversions": {...}, "srcsets": {...}}, ...]}

Multi-collection models stay possible via :meth:`media_in` and
:meth:`clear_media_in`, but the single-collection case is the default and
needs zero configuration.
"""

from __future__ import annotations

import base64 as _base64
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO, ClassVar, TypeGuard, Union, cast

from arvel.database.orm._eager import clear_eager_relation, get_eager_relation
from arvel.database.orm.morph import MorphMany
from arvel.database.orm.morph_map import get_morph_alias
from sqlalchemy import asc, nullslast

from arvel_image.media.exceptions import MediaError
from arvel_image.media.model import Media

_MEDIA_RELATION_KEY = "media"

if TYPE_CHECKING:
    from arvel.database import Model

    from arvel_image.media.collection import MediaCollection
    from arvel_image.media.file_adder import FileAdder

# Any value the polymorphic add_image() can accept.
MediaSource = Union[str, "os.PathLike[str]", bytes, bytearray, memoryview, BinaryIO]

_DATA_URI_RE = re.compile(r"^data:[^;]+;base64,", re.IGNORECASE)
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
# Detects any scheme-prefixed string so we can reject non-http schemes early
# (file:// SSRF, ftp://, gopher://, etc.) instead of misinterpreting them as
# local filesystem paths.
_ANY_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.\-]*://", re.IGNORECASE)
_DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MiB
# Heuristic threshold: anything shorter is far more likely a filename / path
# than a real base64 payload (44 chars decodes to ~32 raw bytes — tiny).
_BASE64_MIN_LEN = 64


def read_from_file_like(source: object, file_name: str | None) -> tuple[bytes, str]:
    """Pull bytes out of any read()-able object. Module-internal."""
    if not file_name:
        msg = (
            "file_name is required for file-like sources — the framework can't "
            "derive one from the read() call alone."
        )
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
    msg = (
        f"file-like object {type(source).__name__!r}.read() returned "
        f"{type(data).__name__}; expected bytes, str, bytearray, or memoryview."
    )
    raise MediaError(msg)


def _ordered(rows: list[Media]) -> list[Media]:
    # Matches the SQL: order_column asc nulls last, then id asc.
    return sorted(rows, key=lambda m: (m.order_column is None, m.order_column or 0, m.id))


async def query_media(host: HasMedia, collection: str) -> list[Media]:
    """Direct DB fetch — used by write paths that can't trust the eager cache."""
    query = (
        Media.query()
        .where(Media.model_type == get_morph_alias(type(host)))
        .where(Media.model_id == str(host.host_pk()))
        .where(Media.collection_name == collection)
        .order_by(nullslast(asc(Media.__table__.c.order_column)), asc(Media.__table__.c.id))
    )
    return list(await query.all())


def _apply_dict_filters(rows: list[Media], criteria: dict[str, Any]) -> list[Media]:
    return [m for m in rows if all(m.custom_properties.get(k) == v for k, v in criteria.items())]


def _is_dict_filter(
    v: dict[str, Any] | Callable[[Media], bool] | None,
) -> TypeGuard[dict[str, Any]]:
    return isinstance(v, dict)


class HasMedia:
    """Polymorphic media on any host model.

    Inherit alongside :class:`~arvel.database.Model`::

        class Product(HasMedia, Model):
            __media_collection__ = "images"

    All read methods (``media``, ``first_media``, ``last_media``, ``image_url``)
    target ``__media_collection__`` directly — no per-call ``collection=`` arg.
    For hosts with multiple collections use :meth:`media_in` / :meth:`clear_media_in`.

    The MRO order matters — ``HasMedia`` must come **before** any base that
    defines ``to_dict``. The framework enforces this at class-definition time
    (see :meth:`__init_subclass__`).
    """

    #: The MorphMany descriptor. ``with_("media")`` loads it.
    media: MorphMany[Media] = MorphMany(Media, name="model")

    #: Bucket name used for every upload / read on this model. Override per host.
    __media_collection__: ClassVar[str] = "default"

    __arvel_media_collections__: ClassVar[dict[str, Any]] = {}
    __arvel_collections_registered__: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        # Guard against the silent-data-loss MRO trap: HasMedia.to_dict() chains
        # via super(). If any class earlier in MRO defines to_dict, ours never
        # runs and `media` quietly drops from the serialized output.
        super().__init_subclass__(**kwargs)
        mro = cls.__mro__
        hasmedia_idx = mro.index(HasMedia)
        for ancestor in mro[1:hasmedia_idx]:
            if "to_dict" in ancestor.__dict__:
                msg = (
                    f"{cls.__name__}: HasMedia must come before {ancestor.__name__} "
                    f"in the base class list — otherwise HasMedia.to_dict() is "
                    f"shadowed and `media` will silently drop from serialization. "
                    f"Write `class {cls.__name__}(HasMedia, {ancestor.__name__}, ...)`."
                )
                raise TypeError(msg)

    # ── overridable hook ───────────────────────────────────────────────────

    def register_media_collections(self) -> None:
        """Auto-registers ``__media_collection__`` using the matching preset.

        Silently no-ops when no preset is registered for the name — hosts
        without explicit collections still work with an implicit
        :class:`MediaCollection`. Override when you need ``accepts_file``
        callbacks or want to register multiple collections explicitly.
        """
        from arvel_image.media.presets import get_collection_preset  # noqa: PLC0415

        try:
            preset = get_collection_preset(type(self).__media_collection__)
        except KeyError:
            return
        preset.register_on(self)

    # ── single-collection reads ────────────────────────────────────────────

    def get_media(
        self,
        *,
        filters: dict[str, Any] | Callable[[Media], bool] | None = None,
    ) -> list[Media]:
        """Eager-loaded media for ``__media_collection__``, ordered by ``order_column, id``.

        Reads from ``self.media``; raises ``LazyLoadingError`` when the
        relation wasn't eager-loaded.
        """
        return self.media_in(type(self).__media_collection__, filters=filters)

    @property
    def first_media(self) -> Media | None:
        """First media in this model's collection, or ``None``."""
        rows = self.get_media()
        return rows[0] if rows else None

    @property
    def last_media(self) -> Media | None:
        """Last media in this model's collection (highest ``order_column``)."""
        rows = self.get_media()
        return rows[-1] if rows else None

    def image_url(
        self,
        conversion: str | None = None,
        *,
        fallback: str | None = None,
    ) -> str | None:
        """URL of the first media's original (or named conversion).

        Falls back to ``fallback`` then the collection's configured fallback URL
        when the collection is empty.
        """
        first = self.first_media
        if first is not None:
            return first.url(conversion)
        if fallback is not None:
            return fallback
        try:
            return self.collection_for(type(self).__media_collection__).get_fallback_url(conversion)
        except Exception:  # noqa: BLE001
            # Collection lookup can raise UnknownCollectionError or fallback
            # resolver-specific errors — none of which should bubble up from
            # what's a read-only convenience accessor.
            return None

    # ── single-collection writes ───────────────────────────────────────────

    async def add_image(
        self,
        source: MediaSource,
        *,
        file_name: str | None = None,
        collection: str | None = None,
        max_bytes: int = _DEFAULT_MAX_BYTES,
    ) -> Media:
        """Ingest ``source`` into ``collection`` (defaults to ``__media_collection__``).

        Accepts: ``bytes`` / ``bytearray`` / ``memoryview`` (need ``file_name``),
        a file path (``str`` / ``PathLike``), an ``http(s)://`` URL (fetched with
        SSRF guard), a ``data:...;base64,`` URI, a base64 string, or any
        file-like object with ``.read()``.

        For custom properties, disk override, queued conversions, or
        responsive toggles, use :meth:`image_builder` for the chain form.
        """
        contents, resolved_name = await self.coerce_source(
            source, file_name=file_name, max_bytes=max_bytes
        )
        from arvel_image.media.file_adder import FileAdder  # noqa: PLC0415

        return await FileAdder(self, contents, file_name=resolved_name).save(collection=collection)

    def image_builder(
        self,
        source: MediaSource,
        *,
        file_name: str | None = None,
    ) -> FileAdder:
        """Builder for advanced uploads — chain ``.with_properties(...)``,
        ``.to_disk(...)``, ``.queued()``, ``.with_responsive_images()``,
        then ``await .save(collection=...)``.

        Only accepts in-memory sources (bytes, file-like, file path). For
        URLs / base64, use :meth:`add_image` directly.
        """
        from arvel_image.media.file_adder import FileAdder  # noqa: PLC0415

        contents, resolved_name = coerce_sync_source(source, file_name)
        return FileAdder(self, contents, file_name=resolved_name)

    async def clear_images(self) -> int:
        """Delete every media + file in this model's collection. Returns count."""
        return await self.clear_media_in(type(self).__media_collection__)

    # ── multi-collection escape hatch ──────────────────────────────────────

    def media_in(
        self,
        collection: str,
        *,
        filters: dict[str, Any] | Callable[[Media], bool] | None = None,
    ) -> list[Media]:
        """Read media from a specific collection (use for multi-collection hosts).

        ``"*"`` returns every collection's media merged. Reads from the eager cache.
        """
        rows = _ordered(self.media)
        if collection != "*":
            rows = [m for m in rows if m.collection_name == collection]

        if filters is None:
            return rows
        if _is_dict_filter(filters):
            return _apply_dict_filters(rows, filters)
        if callable(filters):
            return [m for m in rows if filters(m)]
        return rows

    async def clear_media_in(self, collection: str) -> int:
        """Delete every media + file in ``collection``. Returns the row count."""
        rows = await query_media(self, collection)
        for media in rows:
            await media.delete()
        clear_eager_relation(self, _MEDIA_RELATION_KEY)
        return len(rows)

    async def clear_media_in_except(
        self,
        collection: str,
        kept: Media | list[Media],
    ) -> int:
        """Delete media in ``collection`` except ``kept`` (single or list)."""
        kept_list = [kept] if isinstance(kept, Media) else list(kept)
        kept_ids = {m.id for m in kept_list}
        rows = await query_media(self, collection)
        deleted = 0
        for media in rows:
            if media.id not in kept_ids:
                await media.delete()
                deleted += 1
        clear_eager_relation(self, _MEDIA_RELATION_KEY)
        return deleted

    # ── serialization (the cast) ───────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Append ``media`` to the parent ``to_dict()`` when eager-loaded.

        Each :class:`Media` row is serialized via its own ``to_dict()`` — no
        kit-side serializers, no manual ``[m.to_dict() for m in product.media]``.
        Falls through silently when the relation wasn't loaded (no surprise
        DB hits during serialization).
        """
        # super() in a mixin: at runtime the next class in MRO is Model,
        # which provides to_dict() -> dict[str, Any]. Cast for the type checker.
        data = cast("dict[str, Any]", super().to_dict())  # type: ignore[misc]
        cached_raw = get_eager_relation(self, _MEDIA_RELATION_KEY)
        if cached_raw is not None:
            cached: list[Media] = cast("list[Media]", cached_raw)
            coll = type(self).__media_collection__
            data["media"] = [m.to_dict() for m in cached if m.collection_name == coll]
        return data

    # ── source coercion ────────────────────────────────────────────────────

    async def coerce_source(
        self,
        source: MediaSource,
        *,
        file_name: str | None,
        max_bytes: int,
    ) -> tuple[bytes, str]:
        """Reduce any supported source to ``(bytes, file_name)``. Used by add_image."""
        # bytes-like
        if isinstance(source, (bytes, bytearray, memoryview)):
            if not file_name:
                msg = (
                    f"file_name is required for {type(source).__name__} sources — "
                    "raw bytes have no inherent name."
                )
                raise MediaError(msg)
            return bytes(source), file_name

        # strings: URL → fetch, data: URI → decode, otherwise treat as path
        if isinstance(source, str):
            if _URL_RE.match(source):
                return await _fetch_remote(source, file_name=file_name, max_bytes=max_bytes)
            if _ANY_SCHEME_RE.match(source):
                # file://, ftp://, gopher://, etc. — never silently treat as a path.
                scheme = source.split("://", 1)[0]
                msg = (
                    f"Unsupported URL scheme {scheme!r} in {source!r}; "
                    "only http and https are allowed."
                )
                raise MediaError(msg)
            if _DATA_URI_RE.match(source) or is_base64_payload(source):
                return decode_base64(source, file_name=file_name, max_bytes=max_bytes)
            return read_from_path(source, file_name)

        if isinstance(source, os.PathLike):
            return read_from_path(source, file_name)

        if callable(getattr(source, "read", None)):
            return read_from_file_like(source, file_name)

        msg = (
            f"Unsupported media source type {type(source).__name__!r}. "
            "Accepted: bytes / bytearray / memoryview, str (URL / data URI / "
            "base64 / file path), os.PathLike, or file-like with read()."
        )
        raise MediaError(msg)

    # ── helpers wired by FileAdder / clear ─────────────────────────────────

    def collection_for(self, name: str) -> MediaCollection:
        """Resolve a :class:`MediaCollection` config by name (auto-registers on first use)."""
        from arvel_image.media.collection import MediaCollection  # noqa: PLC0415
        from arvel_image.media.exceptions import UnknownCollectionError  # noqa: PLC0415

        self._ensure_collections()
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

    def get_registered_media_collections(self) -> list[MediaCollection]:
        """Every :class:`MediaCollection` configured for this host."""
        self._ensure_collections()
        cls = type(self)
        registry: dict[str, MediaCollection] = cls.__dict__.get("__arvel_media_collections__") or {}
        return list(registry.values())

    def host_pk(self) -> str:
        """Primary key as a string (varchar column on the media table)."""
        return str(cast("Model", self).get_key())

    async def delete_preserving_media(self) -> Any:
        """Delete the host row without touching the Media rows or files."""
        from arvel.database import Model  # noqa: PLC0415

        # Unbound delete bypasses any media-cascading delete a host overrides.
        return await Model.delete(cast("Model", self))

    def _ensure_collections(self) -> None:
        cls = type(self)
        if cls.__dict__.get("__arvel_collections_registered__"):
            return
        cls.__arvel_media_collections__ = {}
        self.register_media_collections()
        cls.__arvel_collections_registered__ = True


# ── source helpers (module-level, reused by add_image and image_builder) ───


def coerce_sync_source(source: MediaSource, file_name: str | None) -> tuple[bytes, str]:
    """Sync subset — bytes, file path, or file-like. Raises on URL / base64."""
    if isinstance(source, (bytes, bytearray, memoryview)):
        if not file_name:
            msg = (
                f"file_name is required for {type(source).__name__} sources — "
                "raw bytes have no inherent name."
            )
            raise MediaError(msg)
        return bytes(source), file_name
    if isinstance(source, (str, os.PathLike)):
        return read_from_path(source, file_name)
    if callable(getattr(source, "read", None)):
        return read_from_file_like(source, file_name)
    msg = (
        f"image_builder accepts bytes, file paths, or file-like objects; "
        f"got {type(source).__name__}. Use add_image() directly for URLs / base64."
    )
    raise MediaError(msg)


def read_from_path(source: str | os.PathLike[str], file_name: str | None) -> tuple[bytes, str]:
    """Load a file path into (bytes, name). Wraps OSError as MediaError."""
    path = Path(os.fspath(source))
    try:
        contents = path.read_bytes()
    except OSError as exc:
        msg = f"Could not read media from {path}: {exc}"
        raise MediaError(msg) from exc
    return contents, file_name or path.name


async def _fetch_remote(url: str, *, file_name: str | None, max_bytes: int) -> tuple[bytes, str]:
    from arvel_image.media.file_adder import FileAdder  # noqa: PLC0415
    from arvel_image.media.url_fetcher import fetch_url  # noqa: PLC0415

    contents, derived_name = await fetch_url(url, max_bytes=max_bytes)
    return contents, FileAdder.sanitize_file_name(file_name or derived_name)


def decode_base64(data: str, *, file_name: str | None, max_bytes: int) -> tuple[bytes, str]:
    """Decode a base64 / data: URI string into (bytes, sanitized name)."""
    from arvel_image.media.exceptions import FileTooLargeError  # noqa: PLC0415

    if not file_name:
        msg = (
            "file_name is required for base64 sources — the encoded payload "
            "carries no original name."
        )
        raise MediaError(msg)
    raw = _DATA_URI_RE.sub("", data)
    try:
        contents = _base64.b64decode(raw, validate=True)
    except Exception as exc:
        # Wrap-and-rethrow so callers only need to handle MediaError, not
        # binascii.Error / ValueError / etc. from the base64 module.
        msg = f"Invalid base64 data (input was {len(raw)} encoded chars): {exc}"
        raise MediaError(msg) from exc
    if len(contents) > max_bytes:
        msg = f"Decoded base64 is {len(contents)} bytes; exceeds max_bytes={max_bytes}."
        raise FileTooLargeError(msg)
    from arvel_image.media.file_adder import FileAdder  # noqa: PLC0415

    return contents, FileAdder.sanitize_file_name(file_name)


def is_base64_payload(s: str) -> bool:
    """Heuristic: long, even-length string with only base64 chars (and padding).

    Used as a last-resort branch after URL / data-URI checks fail. Treating
    short strings as base64 would steal legitimate filenames.
    """
    if len(s) < _BASE64_MIN_LEN or len(s) % 4 != 0:
        return False
    return all(c.isalnum() or c in "+/=" for c in s)


__all__ = ["HasMedia", "MediaSource"]
