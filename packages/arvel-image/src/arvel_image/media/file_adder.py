"""Builder returned by :meth:`HasMedia.add_media` — terminate with
``await fa.to_media_collection(name)``.

Handles input sanitization (SEC-026-01), single-file collection semantics,
MIME/size validation, UUID auto-assignment, atomic rollback, custom
properties, per-ingestion disk override, and conversion fan-out.
"""

from __future__ import annotations

import logging
import mimetypes
import re
import uuid as _uuid_module
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Self, cast

from arvel_image.media.collection import FileInfo, MediaCollection
from arvel_image.media.conversion_runner import ConversionRunner
from arvel_image.media.exceptions import (
    FileTooLargeError,
    InvalidMimeTypeError,
    MediaError,
)
from arvel_image.media.model import Media

if TYPE_CHECKING:
    from arvel_image.media.path_generator import PathGenerator
    from arvel_image.media.trait import HasMedia

_log = logging.getLogger(__name__)

# Strip control characters (NUL, ESC, newline, …) from caller-provided
# filenames before treating them as basenames. POSIX-friendly: 0x00..0x1f
# plus 0x7f (DEL).
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")


def resolve_path_generator() -> PathGenerator:
    """Return the active path generator (custom or default) (FR-050-28)."""
    from arvel_image.media.path_generator import get_path_generator  # noqa: PLC0415

    return get_path_generator()


class FileAdder:
    """Builder bound to a host model. ``await .to_media_collection(name)``
    persists, runs conversions, and returns the new :class:`Media` row.
    """

    def __init__(
        self,
        host: HasMedia,
        contents: bytes | bytearray | memoryview,
        *,
        file_name: str,
    ) -> None:
        self._host = host
        self._contents = bytes(contents)
        self._file_name = self.sanitize_file_name(file_name)
        self._name = PurePosixPath(self._file_name).stem
        self._mime: str = self._detect_mime(self._file_name)
        self._custom_props: dict[str, Any] = {}
        self._disk_override: str | None = None
        self._file_name_override: str | None = None
        self._sanitize_callback: Callable[[str], str] | None = None
        self._queue_conversions: bool = False

    # ─── public chain ──────────────────────────────────────────────────────

    def queued(self) -> Self:
        """Defer conversions to a :class:`QueuedConversionJob` instead of running inline.

        The job is dispatched after the media row is committed, so it sees
        the persisted file immediately.  Use this for large or slow conversion
        pipelines that would otherwise block the upload request.
        """
        self._queue_conversions = True
        return self

    def use_name(self, name: str) -> Self:
        """Override the human-readable name (defaults to the file stem)."""
        self._name = name
        return self

    def with_custom_properties(self, props: dict[str, Any]) -> Self:
        """Merge ``props`` into the custom_properties stored on the row (FR-046-06)."""
        self._custom_props = {**self._custom_props, **props}
        return self

    def with_properties(self, props: dict[str, Any]) -> Self:
        """Alias for :meth:`with_custom_properties`."""
        return self.with_custom_properties(props)

    def to_disk(self, name: str) -> Self:
        """Override the collection's disk for this specific ingestion (FR-046-09)."""
        self._disk_override = name
        return self

    def using_file_name(self, name: str) -> Self:
        """Override the stored file name (FR-050-21)."""
        self._file_name_override = name
        return self

    def set_file_name(self, name: str) -> Self:
        """Alias for :meth:`using_file_name` (FR-050-21)."""
        return self.using_file_name(name)

    def sanitizing_file_name(self, callback: Callable[[str], str]) -> Self:
        """Register a custom sanitization callback applied after the built-in strip (FR-050-24)."""
        self._sanitize_callback = callback
        return self

    async def to_media_collection(
        self, collection: str = "default", disk: str | None = None
    ) -> Media:
        """Persist the original, register the row, run conversions.

        Validates MIME and size before any I/O (FR-046-07).
        Assigns a UUID4 to the row (FR-046-01).
        Rolls back row + file on any post-creation exception (FR-046-02).
        Honours conversions_disk when set on the collection (FR-046-03).
        Prunes only_keep_latest after successful add (FR-046-12).
        Auto-assigns order_column (FR-050-04).
        ``disk`` arg overrides both .to_disk() and collection.disk (FR-050-10).
        """
        from arvel.facades.storage import Storage  # noqa: PLC0415

        host = self._host
        coll = host.collection_for(collection)

        # Apply file_name override and custom sanitize callback (FR-050-21/24).
        effective_file_name = self._apply_file_name_overrides(
            self._file_name_override or self._file_name
        )
        self._file_name = effective_file_name
        self._name = PurePosixPath(effective_file_name).stem
        self._mime = self._detect_mime(effective_file_name)

        self._validate(coll, collection)

        # ── single_file cleanup ────────────────────────────────────────────
        if coll.single_file:
            await host.clear_media_collection(collection)

        # ── disk resolution ────────────────────────────────────────────────
        # FR-050-10: to_media_collection(disk) > .to_disk() > collection.disk
        disk_label = disk or self._disk_override or coll.disk or "default"
        disk_target: str | None = None if disk_label == "default" else disk_label

        # ── order_column (FR-050-04) ───────────────────────────────────────
        from arvel_image.media.trait import get_media_ordered  # noqa: PLC0415

        existing = await get_media_ordered(host, collection)
        if existing and existing[-1].order_column is not None:
            next_order: int = existing[-1].order_column + 1
        else:
            next_order = 1

        # ── row creation ───────────────────────────────────────────────────
        media = cast(
            "Media",
            await Media.create(
                model_type=type(host).__name__,
                model_id=str(host.host_pk()),  # always string (FR-046-08)
                collection_name=collection,
                name=self._name,
                file_name=self._file_name,
                disk=disk_label,
                size=len(self._contents),
                custom_properties=self._custom_props,
            ),
        )
        # Assign UUID4 after row creation so we have the id (FR-046-01).
        media.uuid = str(_uuid_module.uuid4())
        media.mime_type = self._mime
        media.order_column = next_order

        # ── write original + run conversions (with rollback on failure) ────
        gen: PathGenerator = resolve_path_generator()
        storage_disk = Storage.disk(disk_target)

        try:
            await storage_disk.put(gen.path_for(media), self._contents)

            if coll.conversions:
                if self._queue_conversions:
                    await self._dispatch_conversion_job(media)
                else:
                    await self._run_conversions(media, coll, storage_disk, gen)

            await media.save()

        except Exception:
            try:
                await media.delete()
            except Exception as cleanup_exc:  # noqa: BLE001
                _log.warning("rollback: failed to delete media row %s: %s", media.id, cleanup_exc)
            raise

        # ── prune only_keep_latest ─────────────────────────────────────────
        if coll.keep_latest_n is not None:
            await self._prune_keep_latest(host, collection, coll.keep_latest_n)

        return media

    def _validate(self, coll: MediaCollection, collection: str) -> None:
        """Raise if MIME, size, or accepts_file checks fail (FR-046-07, FR-050-25)."""
        if (
            coll.accept_mime_types_list is not None
            and self._mime.lower() not in coll.accept_mime_types_list
        ):
            msg = (
                f"Invalid MIME type '{self._mime}' for collection '{collection}'; "
                f"allowed: {coll.accept_mime_types_list}"
            )
            raise InvalidMimeTypeError(msg)

        if coll.max_file_size_bytes is not None and len(self._contents) > coll.max_file_size_bytes:
            msg = (
                f"File too large: {len(self._contents)} bytes exceeds "
                f"max_file_size={coll.max_file_size_bytes} for collection '{collection}'"
            )
            raise FileTooLargeError(msg)

        file_info = FileInfo(file_name=self._file_name, mime_type=self._mime)
        if not coll.check_accepts_file(file_info):
            msg = (
                f"File '{self._file_name}' (MIME: {self._mime}) rejected by "
                f"accepts_file callback for collection '{collection}'"
            )
            raise InvalidMimeTypeError(msg)

    def _apply_file_name_overrides(self, name: str) -> str:
        """Apply using_file_name override then sanitize_callback (FR-050-21/24)."""
        cleaned = self.sanitize_file_name(name)
        if self._sanitize_callback is not None:
            cleaned = self._sanitize_callback(cleaned)
            # Re-validate after callback to ensure it's still a safe name.
            cleaned = PurePosixPath(cleaned).name.strip()
            if not cleaned or cleaned in {".", ".."}:
                msg = f"sanitizing_file_name callback produced an invalid name: {cleaned!r}"
                raise MediaError(msg)
        return cleaned

    # ─── queued conversion dispatch ────────────────────────────────────────

    async def _dispatch_conversion_job(self, media: Media) -> None:
        from arvel.facades.bus import Bus  # noqa: PLC0415

        from arvel_image.media.jobs import QueuedConversionJob  # noqa: PLC0415

        host_cls = type(self._host)
        class_path = f"{host_cls.__module__}.{host_cls.__qualname__}"
        await Bus.dispatch(QueuedConversionJob(media_id=str(media.id), model_class_path=class_path))

    # ─── conversions ───────────────────────────────────────────────────────

    async def _run_conversions(
        self,
        media: Media,
        coll: MediaCollection,
        disk: Any,
        gen: PathGenerator,
    ) -> None:
        from arvel.facades.storage import Storage  # noqa: PLC0415

        runner = ConversionRunner()
        generated: dict[str, Any] = dict(media.generated_conversions or {})

        # Conversion derivatives go to conversions_disk when set (FR-046-03).
        cdisk_label = coll.conversions_disk or coll.disk or "default"
        cdisk_target: str | None = None if cdisk_label == "default" else cdisk_label
        if coll.conversions_disk:
            cdisk = Storage.disk(cdisk_target)
            media.conversions_disk = cdisk_label
        else:
            cdisk = disk

        for conversion in coll.conversions:
            if not conversion.accepts(self._mime):
                continue
            output = await runner.run(source=self._contents, conversion=conversion)
            await cdisk.put(gen.path_for_conversion(media, conversion.name), output)
            generated[conversion.name] = True
        media.generated_conversions = generated

    # ─── keep_latest pruning ───────────────────────────────────────────────

    @staticmethod
    async def _prune_keep_latest(host: HasMedia, collection: str, n: int) -> None:
        """Delete the oldest rows from ``collection`` until at most ``n`` remain."""
        from arvel_image.media.trait import get_media_ordered  # noqa: PLC0415

        rows = await get_media_ordered(host, collection)
        excess = rows[:-n] if n > 0 else rows
        for old in excess:
            await old.delete()

    # ─── sanitization ──────────────────────────────────────────────────────

    @classmethod
    def sanitize_file_name(cls, name: object) -> str:
        """Reduce caller-provided filename to a safe basename (SEC-026-01)."""
        if not isinstance(name, str):
            msg = "file_name must be a string"
            raise MediaError(msg)
        cleaned = _CONTROL_CHAR_RE.sub("", name)
        cleaned = PurePosixPath(cleaned).name.strip()
        if not cleaned or cleaned in {".", ".."}:
            msg = f"Invalid file name: {name!r}"
            raise MediaError(msg)
        return cleaned

    @staticmethod
    def _detect_mime(file_name: str) -> str:
        """Best-effort mime-type detection from the filename suffix."""
        guessed, _ = mimetypes.guess_type(file_name)
        return guessed or "application/octet-stream"


__all__ = ["FileAdder"]
