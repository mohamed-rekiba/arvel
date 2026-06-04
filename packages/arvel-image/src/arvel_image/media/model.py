"""Polymorphic ``media`` row.

Mirrors the schema in
``packages/arvel-image/src/arvel_image/migrations/create_media_table.py``.
``model_type`` stores the host's morph alias (``get_morph_alias`` — its morph-map
entry, ``__morph_class__`` override, or short class name): ``"User"``, not
``"app.models.User"``.

JSON columns default to ``{}`` so callers never have to special-case
``None`` when reading metadata. ``Media.delete()`` cleans the original
plus every successfully-generated conversion best-effort: missing files
do not raise.
"""

from __future__ import annotations

import uuid as _uuid_module
from typing import TYPE_CHECKING, Any, ClassVar, cast

from arvel.database import Model, Timestamps
from arvel.database.columns import big_integer, field, json
from arvel.database.columns import uuid as uuid_column
from arvel.database.orm.morph_map import get_morph_alias

if TYPE_CHECKING:
    from arvel.storage import StorageDisk

    from arvel_image.media.path_generator import PathGenerator
    from arvel_image.media.trait import HasMedia

# Mass-assignment guard : system-managed columns
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
    """Return the active path generator (custom or default)"""
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

    id: int = field(default=None, primary_key=True, init=False)
    model_type: str
    # VARCHAR(36) to support UUID-PK host models .
    model_id: str = field(length=36)
    name: str
    file_name: str
    disk: str
    # BigInteger unsigned — matches migration stub
    size: int = big_integer()

    collection_name: str = "default"
    manipulations: dict[str, Any] = json(default=dict)
    custom_properties: dict[str, Any] = json(default=dict)

    # Set by the system after row creation — kept out of __init__.
    uuid: str | None = uuid_column(
        nullable=True, unique=True, as_uuid=False, init=False, default=None
    )
    mime_type: str | None = field(init=False, default=None)
    conversions_disk: str | None = field(init=False, default=None)
    generated_conversions: dict[str, Any] = json(init=False, default=dict)
    responsive_images: dict[str, Any] = json(init=False, default=dict)
    order_column: int | None = field(index=True, init=False, default=None)

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
        """Disk-relative path of the original or a conversion"""
        gen: PathGenerator = resolve_path_generator()
        return gen.path_for_conversion(self, conversion) if conversion else gen.path_for(self)

    def url(self, conversion: str | None = None) -> str:
        """Storage-disk URL for the original or a conversion."""
        from arvel.facades.storage import Storage  # noqa: PLC0415

        path = self.get_path(conversion)
        disk_target = self.conversions_disk_target() if conversion else self.disk_target()
        return Storage.disk(disk_target).url(path)

    def full_url(self, conversion: str | None = None) -> str:
        """Absolute URL — prepends ``app.url`` if :meth:`url` is path-only."""
        url = self.url(conversion)
        if url.startswith(("http://", "https://")):
            return url
        try:
            from arvel.config import config  # noqa: PLC0415

            base: str = str(config("app.url")).rstrip("/")
            if base:
                return f"{base}/{url.lstrip('/')}"
        except Exception:  # noqa: BLE001
            # No app context available (test harness, CLI script) — fall back
            # to the path-only URL. Importing arvel.config can fail in many ways.
            return url
        return url

    def srcset(self, key: str = "original") -> str:
        """``srcset`` attribute value for the responsive image group ``key``.

        Each entry is ``{url} {width}w``. Returns ``""`` when no variants exist.
        """
        from arvel.facades.storage import Storage  # noqa: PLC0415

        responsive: dict[str, Any] = self.responsive_images or {}
        entry = responsive.get(key, {})
        urls: list[Any] = entry.get("urls", [])
        if not urls:
            return ""
        disk = Storage.disk(self.disk_target())
        parts: list[str] = []
        for u in urls:
            path: str = u.get("path", "")
            width: int = u.get("width", 0)
            if not path or not width:
                continue
            parts.append(f"{disk.url(path)} {width}w")
        return ", ".join(parts)

    def placeholder_svg(self, key: str = "original") -> str:
        """Tiny base64 SVG placeholder for ``key``, or ``""``."""
        responsive: dict[str, Any] = self.responsive_images or {}
        return str(responsive.get(key, {}).get("base64svg", ""))

    def temporary_url(self, expiry: int, conversion: str | None = None) -> str:
        """Time-limited URL of the original or a conversion."""
        from arvel.facades.storage import Storage  # noqa: PLC0415

        path = self.get_path(conversion)
        disk_target = self.conversions_disk_target() if conversion else self.disk_target()
        return Storage.disk(disk_target).temporary_url(path, expiry)

    def conversion_urls(self) -> dict[str, str]:
        """``{conversion_name: url}`` for every successfully generated conversion."""
        generated: dict[str, Any] = self.generated_conversions or {}
        return {name: self.url(name) for name, ok in generated.items() if ok}

    def all_srcsets(self) -> dict[str, str]:
        """``{group_key: srcset}`` for every responsive group with variants.

        Includes ``"original"`` (the original-image responsive group) alongside
        per-conversion groups like ``"card"`` / ``"full"``.
        """
        result: dict[str, str] = {}
        for key in self.responsive_images or {}:
            srcset = self.srcset(key)
            if srcset:
                result[key] = srcset
        return result

    def to_dict(self) -> dict[str, Any]:
        """Frontend-ready payload — URL, every conversion URL, every srcset,
        placeholder, metadata.

        Drop-in for API responses; no caller-side ``url()`` / ``srcset()`` loops.
        """
        return {
            "id": str(self.id),
            "uuid": self.uuid,
            "collection_name": self.collection_name,
            "name": self.name,
            "file_name": self.file_name,
            "mime_type": self.mime_type,
            "size": self.size,
            "disk": self.disk,
            "order": self.order_column,
            "custom_properties": dict(self.custom_properties or {}),
            "url": self.url(),
            "conversions": self.conversion_urls(),
            "srcsets": self.all_srcsets(),
            "placeholder_svg": self.placeholder_svg(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    async def delete(self) -> Any:
        """Remove the row + best-effort cleanup of files on disk.

        Cleans the original, every generated conversion, and every responsive
        image variant. Missing files do not raise — the row is the source of truth.
        """
        from arvel.facades.storage import Storage  # noqa: PLC0415

        gen: PathGenerator = resolve_path_generator()
        try:
            disk = Storage.disk(self.disk_target())
        except Exception:  # noqa: BLE001
            # Storage facade can raise UnknownDiskError, config-driven
            # exceptions, or backend init errors — none should block the
            # row delete. Carry on without cleanup; orphan bytes get
            # collected by the storage layer's own GC.
            disk = None

        if disk is not None:
            await _delete_quiet(disk, gen.path_for(self))
            generated: dict[str, Any] = self.generated_conversions or {}
            for conv_name, was_generated in generated.items():
                if was_generated:
                    try:
                        cdisk = Storage.disk(self.conversions_disk_target())
                    except Exception:  # noqa: BLE001
                        # Conversions disk lookup failed — fall back to the
                        # main disk so the cleanup still tries.
                        cdisk = disk
                    await _delete_quiet(cdisk, gen.path_for_conversion(self, conv_name))

            responsive: dict[str, Any] = self.responsive_images or {}
            if responsive:
                from arvel_image.media.responsive_image_generator import (  # noqa: PLC0415
                    delete_responsive_images,
                )

                await delete_responsive_images(responsive, disk=disk)

        return await super().delete()

    async def copy(self, target: HasMedia, collection: str = "default") -> Media:
        """Copy this media to ``target`` host in ``collection``.

        Uses ``target.host_pk()`` for model_id. Copies the original file,
        generated conversion files, and responsive image variant files.
        All file copies are best-effort — a missing file doesn't abort the row copy.
        """
        from arvel.facades.storage import Storage  # noqa: PLC0415

        gen: PathGenerator = resolve_path_generator()
        src_disk = Storage.disk(self.disk_target())
        contents = await src_disk.get(gen.path_for(self))

        new_media: Media = await Media.create(
            model_type=get_morph_alias(type(target)),
            model_id=str(target.host_pk()),  # use host_pk()
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

        # carry generated_conversions and copy conversion files.
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

        # copy responsive image variant files and rewrite paths for the new ID.
        src_responsive: dict[str, Any] = self.responsive_images or {}
        if src_responsive:
            from arvel_image.media.responsive_image_generator import (  # noqa: PLC0415
                copy_responsive_images,
            )

            new_media.responsive_images = await copy_responsive_images(
                src_responsive, new_media.id, disk=dst_disk
            )

        await new_media.save()
        return new_media

    async def move(self, target: HasMedia, collection: str = "default") -> Media:
        """Move this media to ``target`` host in ``collection``

        Updates the row in place — no new file copy on disk (same path).
        Uses ``target.host_pk()`` for model_id
        """
        self.model_type = get_morph_alias(type(target))
        self.model_id = str(target.host_pk())  # use host_pk()
        self.collection_name = collection
        await self.save()
        return self

    # ─── custom property helpers ───────────────────────────────────────────

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

    # ─── QoL helpers ───────────────────────────────────────────────────────

    def has_generated_conversion(self, name: str) -> bool:
        """Return ``True`` if conversion ``name`` was generated successfully."""
        return bool((self.generated_conversions or {}).get(name))

    @property
    def human_readable_size(self) -> str:
        """Return file size as a human-readable string"""
        size = self.size or 0
        if size < _KB:
            return f"{size} B"
        if size < _MB:
            return f"{size / _KB:.1f} KB"
        if size < _GB:
            return f"{size / _MB:.1f} MB"
        return f"{size / _GB:.1f} GB"

    # ─── set_new_order ─────────────────────────────────────────────────────

    @classmethod
    async def set_new_order(
        cls,
        ids: list[int],
        *,
        start_order: int = 1,
    ) -> None:
        """Bulk-update ``order_column`` for the given IDs

        Unknown IDs are silently skipped. ``start_order`` defaults to 1.
        """
        # Fetch only the IDs that exist to skip unknowns safely.
        existing_ids = set(await cls.query().where_in("id", ids).pluck("id"))

        for position, media_id in enumerate(ids, start=start_order):
            if media_id not in existing_ids:
                continue
            await cls.query().where(cls.id == media_id).update({"order_column": position})


async def _delete_quiet(disk: StorageDisk, path: str) -> None:
    """Delete ``path`` on ``disk``, swallowing missing-file/disk errors."""
    try:
        await disk.delete(path)
    except FileNotFoundError:
        return
    except Exception:  # noqa: BLE001
        # Best-effort cleanup. Driver-specific failures (S3 NoSuchKey,
        # permission denied, transient network) shouldn't propagate from
        # a delete cascade; the storage GC catches the orphan.
        return


__all__ = ["Media"]
