"""Polymorphic ``media`` row — Spatie laravel-medialibrary v11 parity.

Mirrors the schema in
``packages/arvel-image/src/arvel_image/migrations/create_media_table.py``.
Discriminator columns use the host's short class name (ADR-022 +
ADR-082 D2): ``model_type`` is ``"User"``, not ``"app.models.User"``.

JSON columns default to ``{}`` so callers never have to special-case
``None`` when reading metadata. ``Media.delete()`` cleans the original
plus every successfully-generated conversion best-effort: missing files
do not raise (FR-026-39).
"""

from __future__ import annotations

import uuid as _uuid_module
from typing import TYPE_CHECKING, Any, ClassVar, cast

from arvel.database import Model, Timestamps
from arvel.database.columns import big_integer, id_, string
from sqlalchemy import JSON, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

if TYPE_CHECKING:
    from arvel_image.media.path_generator import PathGenerator
    from arvel_image.media.trait import HasMedia

# Mass-assignment guard (FR-026-9 / SEC-026-04): system-managed columns
# (``id``, ``uuid``, timestamps) and best-effort metadata are NOT fillable
# from user input. Internal callers set those fields via attribute assignment.
_FILLABLE: tuple[str, ...] = (
    "model_type",
    "model_id",
    "collection_name",
    "name",
    "file_name",
    "disk",
    "size",
    "manipulations",
    "custom_properties",
)

_KB = 1024
_MB = _KB * _KB
_GB = _KB * _MB


def resolve_path_generator() -> PathGenerator:
    """Return the active path generator (custom or default) (FR-050-28)."""
    from arvel_image.media.path_generator import get_path_generator  # noqa: PLC0415

    return get_path_generator()


class Media(Model, Timestamps):
    """Polymorphic media row associated with any host via (model_type, model_id)."""

    __tablename__ = "media"
    __fillable__: ClassVar[list[str] | None] = list(_FILLABLE)

    __casts__: ClassVar[dict[str, str]] = {
        "manipulations": "dict",
        "custom_properties": "dict",
        "generated_conversions": "dict",
        "responsive_images": "dict",
    }

    id: Mapped[int] = id_(init=False)
    model_type: Mapped[str] = string(255)
    # VARCHAR(36) to support UUID-PK host models (ADR-108, FR-046-08).
    model_id: Mapped[str] = string(36)
    name: Mapped[str] = string(255)
    file_name: Mapped[str] = string(255)
    disk: Mapped[str] = string(255)
    # BigInteger unsigned — matches migration stub (FR-046-15).
    size: Mapped[int] = big_integer()

    # Defaulted (init=True, with default)
    collection_name: Mapped[str] = string(255, default="default")
    manipulations: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default_factory=dict
    )
    custom_properties: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default_factory=dict
    )

    # Fields set by the system after row creation (not in __init__)
    uuid: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), nullable=True, unique=True, init=False, default=None
    )
    mime_type: Mapped[str | None] = mapped_column(
        String(255), nullable=True, init=False, default=None
    )
    conversions_disk: Mapped[str | None] = mapped_column(
        String(255), nullable=True, init=False, default=None
    )
    generated_conversions: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, init=False, default_factory=dict
    )
    responsive_images: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, init=False, default_factory=dict
    )
    order_column: Mapped[int | None] = mapped_column(
        Integer, nullable=True, init=False, default=None
    )

    __table_args__ = (Index("media_order_column_index", "order_column"),)

    # ─── helpers ───────────────────────────────────────────────────────────

    def disk_target(self) -> str | None:
        """Translate the persisted ``disk`` label to a Storage facade target.

        ``"default"`` is a human-readable label; we pass ``None`` so the facade
        resolves the configured default disk.
        """
        return None if self.disk == "default" else self.disk

    def conversions_disk_target(self) -> str | None:
        """Return the disk target for conversion derivatives."""
        cdisk = self.conversions_disk
        if not cdisk:
            return self.disk_target()
        return None if cdisk == "default" else cdisk

    def get_path(self, conversion: str | None = None) -> str:
        """Disk-relative path of the original or a conversion (FR-026-4)."""
        gen: PathGenerator = resolve_path_generator()
        return gen.path_for_conversion(self, conversion) if conversion else gen.path_for(self)

    async def get_url(self, conversion: str | None = None) -> str:
        """Return the storage-disk URL for the original or a conversion (FR-026-3)."""
        from arvel.facades.storage import Storage  # noqa: PLC0415

        path = self.get_path(conversion)
        disk_target = self.conversions_disk_target() if conversion else self.disk_target()
        disk = Storage.disk(disk_target)
        return disk.url(path)

    async def get_full_url(self, conversion: str | None = None) -> str:
        """Return an absolute URL for the original or a conversion (FR-050-19).

        If ``get_url()`` already returns an absolute URL this is a transparent alias.
        If it returns a path-only URL, prepends the configured app URL.
        """
        url = await self.get_url(conversion)
        if url.startswith(("http://", "https://")):
            return url
        # Prepend app URL if available, otherwise return as-is.
        try:
            from arvel.config import config  # noqa: PLC0415

            base: str = str(config("app.url")).rstrip("/")
            if base:
                return f"{base}/{url.lstrip('/')}"
        except Exception:  # noqa: BLE001
            return url
        return url

    async def get_temporary_url(self, expiry: int, conversion: str | None = None) -> str:
        """Time-limited URL of the original or a conversion (FR-026-5)."""
        from arvel.facades.storage import Storage  # noqa: PLC0415

        path = self.get_path(conversion)
        disk_target = self.conversions_disk_target() if conversion else self.disk_target()
        disk = Storage.disk(disk_target)
        return disk.temporary_url(path, expiry)

    async def delete(self) -> Any:
        """Remove the row + best-effort cleanup of files on disk.

        Cleans the original AND every conversion marked as generated in
        ``generated_conversions``. Missing files do not raise — the row
        is the source of truth, files are advisory (FR-026-39).
        """
        from arvel.facades.storage import Storage  # noqa: PLC0415

        gen: PathGenerator = resolve_path_generator()
        try:
            disk = Storage.disk(self.disk_target())
        except Exception:  # noqa: BLE001
            disk = None

        if disk is not None:
            await _delete_quiet(disk, gen.path_for(self))
            generated: dict[str, Any] = self.generated_conversions or {}
            for conv_name, was_generated in generated.items():
                if was_generated:
                    try:
                        cdisk = Storage.disk(self.conversions_disk_target())
                    except Exception:  # noqa: BLE001
                        cdisk = disk
                    await _delete_quiet(cdisk, gen.path_for_conversion(self, conv_name))

        return await super().delete()

    async def copy(self, target: HasMedia, collection: str = "default") -> Media:
        """Copy this media to ``target`` host in ``collection`` (FR-046-13, FR-050-07/08).

        Uses ``target.host_pk()`` for model_id (FR-050-07).
        Copies generated conversion files and carries generated_conversions (FR-050-08).
        """
        from arvel.facades.storage import Storage  # noqa: PLC0415

        gen: PathGenerator = resolve_path_generator()
        src_disk = Storage.disk(self.disk_target())
        contents = await src_disk.get(gen.path_for(self))

        new_media: Media = await Media.create(
            model_type=type(target).__name__,
            model_id=str(target.host_pk()),  # FR-050-07: use host_pk()
            collection_name=collection,
            name=self.name,
            file_name=self.file_name,
            disk=self.disk,
            size=self.size,
            manipulations=dict(self.manipulations or {}),
            custom_properties=dict(self.custom_properties or {}),
        )
        new_media.uuid = str(_uuid_module.uuid4())
        new_media.mime_type = self.mime_type

        dst_disk = Storage.disk(new_media.disk_target())
        await dst_disk.put(gen.path_for(new_media), contents)

        # FR-050-08: carry generated_conversions and copy conversion files.
        src_generated: dict[str, Any] = dict(self.generated_conversions or {})
        if src_generated:
            new_media.generated_conversions = src_generated
            for conv_name, was_generated in src_generated.items():
                if was_generated:
                    try:
                        src_cdisk = Storage.disk(self.conversions_disk_target())
                        conv_bytes = await src_cdisk.get(gen.path_for_conversion(self, conv_name))
                        dst_cdisk = Storage.disk(new_media.conversions_disk_target())
                        await dst_cdisk.put(
                            gen.path_for_conversion(new_media, conv_name), conv_bytes
                        )
                    except OSError:
                        continue

        await new_media.save()
        return new_media

    async def move(self, target: HasMedia, collection: str = "default") -> Media:
        """Move this media to ``target`` host in ``collection`` (FR-046-13, FR-050-07).

        Updates the row in place — no new file copy on disk (same path).
        Uses ``target.host_pk()`` for model_id (FR-050-07).
        """
        self.model_type = type(target).__name__
        self.model_id = str(target.host_pk())  # FR-050-07: use host_pk()
        self.collection_name = collection
        await self.save()
        return self

    # ─── custom property helpers (FR-050-16) ───────────────────────────────

    def has_custom_property(self, key: str) -> bool:
        """Return ``True`` if ``key`` exists in ``custom_properties``."""
        props = self.custom_properties or {}
        return key in props

    def get_custom_property(self, key: str, default: Any = None) -> Any:
        """Return the value at ``key`` (dot-notation supported) or ``default``.

        Supports dot notation: ``"group.sub_key"`` navigates nested dicts.
        """
        props: dict[str, Any] = self.custom_properties or {}
        if "." not in key:
            return props.get(key, default)
        parts = key.split(".")
        node: dict[str, Any] = props
        for i, part in enumerate(parts):
            if part not in node:
                return default
            val: Any = node[part]
            if i == len(parts) - 1:
                return val
            if not isinstance(val, dict):
                return default
            node = cast("dict[str, Any]", val)
        return default

    def set_custom_property(self, key: str, value: Any) -> None:
        """Add or update ``key`` in ``custom_properties`` (in memory only)."""
        self.custom_properties[key] = value

    def forget_custom_property(self, key: str) -> None:
        """Remove ``key`` from ``custom_properties`` (in memory only)."""
        props = self.custom_properties or {}
        props.pop(key, None)
        self.custom_properties = props

    # ─── QoL helpers (FR-050-18/20) ────────────────────────────────────────

    def has_generated_conversion(self, name: str) -> bool:
        """Return ``True`` if conversion ``name`` was generated successfully."""
        return bool((self.generated_conversions or {}).get(name))

    @property
    def human_readable_size(self) -> str:
        """Return file size as a human-readable string (FR-050-20)."""
        size = self.size or 0
        if size < _KB:
            return f"{size} B"
        if size < _MB:
            return f"{size / _KB:.1f} KB"
        if size < _GB:
            return f"{size / _MB:.1f} MB"
        return f"{size / _GB:.1f} GB"

    # ─── class method: set_new_order (FR-050-06) ───────────────────────────

    @classmethod
    async def set_new_order(
        cls,
        ids: list[int],
        *,
        start_order: int = 1,
    ) -> None:
        """Bulk-update ``order_column`` for the given IDs (FR-050-06).

        Unknown IDs are silently skipped. ``start_order`` defaults to 1.
        """
        from arvel.database.session import get_active_session  # noqa: PLC0415
        from sqlalchemy import select, update  # noqa: PLC0415

        session = get_active_session()
        # Fetch only the IDs that exist to skip unknowns safely.
        result = await session.execute(select(cls.id).where(cls.id.in_(ids)))
        existing_ids = {row[0] for row in result}

        for position, media_id in enumerate(ids, start=start_order):
            if media_id not in existing_ids:
                continue
            await session.execute(
                update(cls).where(cls.id == media_id).values(order_column=position)
            )


async def _delete_quiet(disk: Any, path: str) -> None:
    """Delete ``path`` on ``disk``, swallowing missing-file/disk errors."""
    try:
        await disk.delete(path)
    except FileNotFoundError:
        return
    except Exception:  # noqa: BLE001
        return


__all__ = ["Media"]
