"""Builder returned by :meth:`HasMedia.image_builder` — terminate with
``await fa.save()``.

Handles input sanitization, single-file collection semantics, MIME/size
validation, UUID auto-assignment, atomic rollback, custom properties,
per-ingestion disk override, and conversion fan-out. The builder is for
advanced uploads; simple ones go through :meth:`HasMedia.add_image`.
"""

from __future__ import annotations

import logging
import mimetypes
import re
import uuid as _uuid_module
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Self, cast

from arvel.database.orm.morph_map import get_morph_alias
from arvel.facades.bus import Bus
from arvel.facades.storage import Storage

from arvel_image.media.collection import FileInfo, MediaCollection
from arvel_image.media.conversion_runner import get_conversion_runner
from arvel_image.media.exceptions import (
    FileTooLargeError,
    InvalidMimeTypeError,
    MediaError,
)
from arvel_image.media.model import Media
from arvel_image.media.trait import query_media
from arvel_image.media.url_fetcher import sniff_image_mime

if TYPE_CHECKING:
    from arvel.database import Model
    from arvel.storage import StorageDisk

    from arvel_image.media.path_generator import PathGenerator
    from arvel_image.media.trait import HasMedia

_log = logging.getLogger(__name__)

# Strip control characters (NUL, ESC, newline, …) from caller-provided
# filenames before treating them as basenames. POSIX-friendly: 0x00..0x1f
# plus 0x7f (DEL).
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")


def resolve_path_generator() -> PathGenerator:
    """Return the active path generator (custom or default)"""
    from arvel_image.media.path_generator import get_path_generator  # noqa: PLC0415

    return get_path_generator()


class FileAdder:
    """Builder bound to a host model. ``await .save()`` persists, runs
    conversions, and returns the new :class:`Media` row.
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
        self._mime: str = self._detect_mime(self._file_name, self._contents)
        self._custom_props: dict[str, Any] = {}
        self._disk_override: str | None = None
        self._file_name_override: str | None = None
        self._sanitize_callback: Callable[[str], str] | None = None
        self._queue_conversions: bool = False
        # None = inherit from collection; True = force on; False = force off
        self._generate_responsive: bool | None = None

    # ─── public chain ──────────────────────────────────────────────────────

    def queued(self) -> Self:
        """Defer conversions to a :class:`QueuedConversionJob` instead of running inline.

        The job is dispatched after the media row is committed, so it sees
        the persisted file immediately.  Use this for large or slow conversion
        pipelines that would otherwise block the upload request.
        """
        self._queue_conversions = True
        return self

    def with_responsive_images(self) -> Self:
        """Generate responsive width variants (srcset) for this upload.

        Alternatively enable for all adds to a collection via
        ``MediaCollection.generate_responsive_images()``.
        """
        self._generate_responsive = True
        return self

    def without_responsive_images(self) -> Self:
        """Opt-out of responsive image generation even when the collection enables it."""
        self._generate_responsive = False
        return self

    def use_name(self, name: str) -> Self:
        """Override the human-readable name (defaults to the file stem)."""
        self._name = name
        return self

    def with_custom_properties(self, props: dict[str, Any]) -> Self:
        """Merge ``props`` into the custom_properties stored on the row"""
        self._custom_props = {**self._custom_props, **props}
        return self

    def with_properties(self, props: dict[str, Any]) -> Self:
        """Alias for :meth:`with_custom_properties`."""
        return self.with_custom_properties(props)

    def to_disk(self, name: str) -> Self:
        """Override the collection's disk for this specific ingestion"""
        self._disk_override = name
        return self

    def using_file_name(self, name: str) -> Self:
        """Override the stored file name"""
        self._file_name_override = name
        return self

    def set_file_name(self, name: str) -> Self:
        """Alias for :meth:`using_file_name`"""
        return self.using_file_name(name)

    def sanitizing_file_name(self, callback: Callable[[str], str]) -> Self:
        """Register a custom sanitization callback applied after the built-in strip"""
        self._sanitize_callback = callback
        return self

    async def save(self, *, collection: str | None = None, disk: str | None = None) -> Media:
        """Persist the original, register the row, run conversions.

        ``collection`` defaults to ``host.__media_collection__``. Validates
        MIME and size before any I/O. Assigns a UUID4. Rolls back row + file
        on any post-creation exception. Honours ``conversions_disk`` when
        set on the collection. Prunes ``only_keep_latest`` after successful
        add. Auto-assigns ``order_column``. The ``disk`` arg overrides both
        ``.to_disk()`` and ``collection.disk``.
        """
        host = self._host
        resolved_collection = collection or type(host).__media_collection__
        coll = host.collection_for(resolved_collection)
        collection = resolved_collection

        # Apply file_name override and custom sanitize callback.
        effective_file_name = self._apply_file_name_overrides(
            self._file_name_override or self._file_name
        )
        self._file_name = effective_file_name
        self._name = PurePosixPath(effective_file_name).stem
        self._mime = self._detect_mime(effective_file_name, self._contents)

        self._validate(coll, collection)

        # ── single_file cleanup ────────────────────────────────────────────
        if coll.single_file_enabled:
            await host.clear_media_in(collection)

        # ── disk resolution ────────────────────────────────────────────────
        # save(disk=...) > .to_disk() > collection.disk
        disk_label = disk or self._disk_override or coll.disk or "default"
        disk_target: str | None = None if disk_label == "default" else disk_label

        # ── order_column ───────────────────────────────────────
        existing = await query_media(host, collection)
        if existing and existing[-1].order_column is not None:
            next_order: int = existing[-1].order_column + 1
        else:
            next_order = 1

        # ── row creation ───────────────────────────────────────────────────
        media = cast(
            "Media",
            await Media.create(
                model_type=get_morph_alias(type(host)),
                model_id=str(host.host_pk()),  # always string
                collection_name=collection,
                name=self._name,
                file_name=self._file_name,
                disk=disk_label,
                size=len(self._contents),
                custom_properties=self._custom_props,
            ),
        )
        # Assign UUID4 after row creation so we have the id
        media.uuid = str(_uuid_module.uuid4())
        media.mime_type = self._mime
        media.order_column = next_order

        # ── write original + run conversions (with rollback on failure) ────
        gen: PathGenerator = resolve_path_generator()
        storage_disk = Storage.disk(disk_target)

        # Explicit opt-in/opt-out takes precedence; collection flag is the default.
        if self._generate_responsive is None:
            should_generate_responsive = coll.responsive_images_enabled
        else:
            should_generate_responsive = self._generate_responsive

        try:
            await storage_disk.put(gen.path_for(media), self._contents)

            if coll.conversions:
                if self._queue_conversions:
                    await self.dispatch_conversion_job(
                        media, generate_responsive=should_generate_responsive
                    )
                else:
                    await self._run_conversions(media, coll, storage_disk, gen)

            # Skip inline responsive images when conversions are queued —
            # the job generates them in the background to keep uploads fast.
            if should_generate_responsive and not self._queue_conversions:
                await self._run_responsive_images(media, storage_disk)

            await media.save()

        except Exception:
            # Broad on purpose: any failure between save() and conversions
            # leaves a stale row + stored bytes. Roll back the row; bytes
            # are best-effort cleaned up by the storage layer's own GC.
            try:
                await media.delete()
            except Exception as cleanup_exc:  # noqa: BLE001
                # Two failures in a row — log and continue raising the original.
                # Don't shadow the original exception with a cleanup failure.
                _log.warning("rollback: failed to delete media row %s: %s", media.id, cleanup_exc)
            raise

        # ── prune only_keep_latest ─────────────────────────────────────────
        if coll.keep_latest_n is not None:
            await self._prune_keep_latest(host, collection, coll.keep_latest_n)

        # Keep host.media in sync so reads right after add work without
        # an explicit `await host.load("media")`.
        await cast("Model", host).load("media")

        return media

    def _validate(self, coll: MediaCollection, collection: str) -> None:
        """Raise if MIME, size, or accepts_file checks fail"""
        if (
            coll.accept_mime_types_list is not None
            and self._mime.lower() not in coll.accept_mime_types_list
        ):
            msg = (
                f"Invalid MIME type {self._mime!r} on file {self._file_name!r} "
                f"for collection {collection!r}; "
                f"allowed: {coll.accept_mime_types_list}"
            )
            raise InvalidMimeTypeError(msg)

        if coll.max_file_size_bytes is not None and len(self._contents) > coll.max_file_size_bytes:
            msg = (
                f"File {self._file_name!r} is too large: {len(self._contents)} bytes "
                f"exceeds max_file_size={coll.max_file_size_bytes} "
                f"for collection {collection!r}"
            )
            raise FileTooLargeError(msg)

        file_info = FileInfo(file_name=self._file_name, mime_type=self._mime)
        if not coll.check_accepts_file(file_info):
            msg = (
                f"File {self._file_name!r} (MIME {self._mime!r}, "
                f"{len(self._contents)} bytes) rejected by "
                f"accepts_file callback for collection {collection!r}"
            )
            raise InvalidMimeTypeError(msg)

    def _apply_file_name_overrides(self, name: str) -> str:
        """Apply using_file_name override then sanitize_callback."""
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

    async def dispatch_conversion_job(
        self, media: Media, *, generate_responsive: bool = False
    ) -> None:
        from arvel_image.media.jobs import QueuedConversionJob  # noqa: PLC0415

        host_cls = self._host.__class__
        class_path = f"{host_cls.__module__}.{host_cls.__qualname__}"
        await Bus.dispatch(
            QueuedConversionJob(
                media_id=str(media.id),
                model_class_path=class_path,
                generate_responsive_images=generate_responsive,
            )
        )

    # ─── conversions ───────────────────────────────────────────────────────

    async def _run_conversions(
        self,
        media: Media,
        coll: MediaCollection,
        disk: StorageDisk,
        gen: PathGenerator,
    ) -> None:
        runner = get_conversion_runner()
        generated: dict[str, Any] = dict(media.generated_conversions or {})

        # Conversion derivatives go to conversions_disk when set
        cdisk_label = coll.conversions_disk or coll.disk or "default"
        cdisk_target: str | None = None if cdisk_label == "default" else cdisk_label
        if coll.conversions_disk:
            cdisk = Storage.disk(cdisk_target)
            media.conversions_disk = cdisk_label
        else:
            cdisk = disk

        manips: dict[str, Any] = media.manipulations or {}
        global_overrides: dict[str, Any] = dict(manips.get("*", {}))

        responsive_updates: dict[str, Any] = {}
        for conversion in coll.conversions:
            if not conversion.accepts(self._mime):
                continue
            conv_overrides: dict[str, Any] = {
                **global_overrides,
                **dict(manips.get(conversion.name, {})),
            }
            effective = (
                conversion.with_manipulations(conv_overrides) if conv_overrides else conversion
            )
            output = await runner.run(
                source=self._contents, conversion=effective, context=f"media id={media.id}"
            )
            await cdisk.put(gen.path_for_conversion(media, conversion.name), output)
            generated[conversion.name] = True

            if conversion.responsive_images_enabled:
                from arvel_image.media.responsive_image_generator import (  # noqa: PLC0415
                    generate_responsive_images_for_media,
                )

                entry = await generate_responsive_images_for_media(
                    media, output, conversion.name, disk=cdisk
                )
                if entry:
                    responsive_updates[conversion.name] = entry

        media.generated_conversions = generated
        if responsive_updates:
            existing_resp = dict(media.responsive_images or {})
            existing_resp.update(responsive_updates)
            media.responsive_images = existing_resp

    async def _run_responsive_images(self, media: Media, disk: StorageDisk) -> None:
        from arvel_image.media.responsive_image_generator import (  # noqa: PLC0415
            generate_responsive_images_for_media,
        )

        entry = await generate_responsive_images_for_media(
            media, self._contents, "original", disk=disk
        )
        if entry:
            existing = dict(media.responsive_images or {})
            existing["original"] = entry
            media.responsive_images = existing

    # ─── keep_latest pruning ───────────────────────────────────────────────

    @staticmethod
    async def _prune_keep_latest(host: HasMedia, collection: str, n: int) -> None:
        """Delete the oldest rows from ``collection`` until at most ``n`` remain."""
        rows = await query_media(host, collection)
        excess = rows[:-n] if n > 0 else rows
        for old in excess:
            await old.delete()

    # ─── sanitization ──────────────────────────────────────────────────────

    @staticmethod
    def sanitize_file_name(name: object) -> str:
        """Reduce caller-provided filename to a safe basename"""
        if not isinstance(name, str):
            msg = f"file_name must be a string; got {type(name).__name__}"
            raise MediaError(msg)
        cleaned = _CONTROL_CHAR_RE.sub("", name)
        cleaned = PurePosixPath(cleaned).name.strip()
        if not cleaned or cleaned in {".", ".."}:
            msg = f"Invalid file name: {name!r}"
            raise MediaError(msg)
        return cleaned

    @staticmethod
    def _detect_mime(file_name: str, contents: bytes) -> str:
        """Detect MIME from file content, falling back to the filename suffix.

        Content wins because the extension is attacker-controlled — a renamed
        ``evil.bin`` must not pass an image-only ``accept_mime_types`` gate.
        Pillow decodes the header to identify the real image format; non-image
        bytes fall back to the extension guess (stdlib ``mimetypes``).
        """
        sniffed = sniff_image_mime(contents)
        if sniffed is not None:
            return sniffed
        guessed, _ = mimetypes.guess_type(file_name)
        return guessed or "application/octet-stream"


__all__ = ["FileAdder"]
