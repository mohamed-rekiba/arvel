"""MediaLibrary service for bulk operations"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from arvel.database.orm.morph_map import get_morph_alias

if TYPE_CHECKING:
    from arvel_image.media.conversion_runner import ConversionRunner
    from arvel_image.media.model import Media
    from arvel_image.media.path_generator import PathGenerator
    from arvel_image.media.trait import HasMedia


@dataclass
class _ConvCtx:
    """Execution context shared across conversions in a single ``process_one`` call."""

    disk: Any
    gen: PathGenerator
    runner: ConversionRunner


def resolve_path_generator() -> PathGenerator:
    """Return the active path generator (custom or default)"""
    from arvel_image.media.path_generator import get_path_generator  # noqa: PLC0415

    return get_path_generator()


class MediaLibrary:
    """Service for bulk media operations.

    Usage::

        lib = MediaLibrary()
        count = await lib.regenerate(host=user, collection="avatar")
        count = await lib.regenerate()  # all rows
    """

    async def regenerate(
        self,
        host: HasMedia | None = None,
        collection: str | None = None,
    ) -> int:
        """Re-run conversions for matching :class:`Media` rows.

         When ``host`` is ``None``, all rows in the media table are processed
        . Reads source files from ``media.disk`` and
         writes conversions to ``media.conversions_disk`` when set

         Returns the count of rows processed.
        """
        from arvel_image.media.model import Media  # noqa: PLC0415

        query = Media.query()
        if host is not None:
            query = query.where(Media.model_type == get_morph_alias(type(host)))
            query = query.where(Media.model_id == str(host.host_pk()))
        if collection is not None:
            query = query.where(Media.collection_name == collection)

        rows: list[Media] = list(await query.all())

        processed = 0
        for media in rows:
            await process_one(media, host)
            processed += 1
        return processed


async def process_one(
    media: Media,
    host: HasMedia | None,
    runner: ConversionRunner | None = None,
    gen: PathGenerator | None = None,
) -> None:
    """Re-run conversions for a single media row. Skips quietly on errors.

    ``runner`` and ``gen`` default to the active module-level singletons when
    not supplied — callers don't need to look them up themselves.
    """
    from arvel.facades.storage import Storage  # noqa: PLC0415

    from arvel_image.media.conversion_runner import (  # noqa: PLC0415
        get_conversion_runner,
    )

    effective_runner = runner if runner is not None else get_conversion_runner()
    effective_gen = gen if gen is not None else resolve_path_generator()

    if not media.mime_type:
        return

    # read from media.disk regardless of whether host is supplied.
    read_disk_label = media.disk
    read_disk_target: str | None = None if read_disk_label == "default" else read_disk_label
    read_disk = Storage.disk(read_disk_target)

    try:
        contents = await read_disk.get(effective_gen.path_for(media))
    except Exception:  # noqa: BLE001
        return

    # Cannot resolve collection config without a host — skip conversions.
    if host is None:
        return

    try:
        coll = host.collection_for(media.collection_name)
    except Exception:  # noqa: BLE001
        return

    if not coll.conversions:
        return

    # write conversions to media.conversions_disk when set.
    if media.conversions_disk:
        write_disk_target: str | None = (
            None if media.conversions_disk == "default" else media.conversions_disk
        )
        write_disk = Storage.disk(write_disk_target)
    else:
        write_disk = read_disk

    ctx = _ConvCtx(disk=write_disk, gen=effective_gen, runner=effective_runner)
    generated, responsive_updates = await _run_conversion_loop(media, coll, contents, ctx)

    if generated:
        media.generated_conversions = {**(media.generated_conversions or {}), **generated}

    if responsive_updates:
        existing_resp = dict(media.responsive_images or {})
        existing_resp.update(responsive_updates)
        media.responsive_images = existing_resp

    await _maybe_regenerate_responsive(media, contents, read_disk)
    await media.save()


async def _run_conversion_loop(
    media: Media,
    coll: Any,
    contents: bytes,
    ctx: _ConvCtx,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run each conversion in ``coll`` against ``contents`` and return
    ``(generated, responsive_updates)`` dicts."""
    manips: dict[str, Any] = media.manipulations or {}
    global_overrides: dict[str, Any] = dict(manips.get("*", {}))
    generated: dict[str, Any] = {}
    responsive_updates: dict[str, Any] = {}

    for conv in coll.conversions:
        if not conv.accepts(media.mime_type):
            continue
        conv_overrides: dict[str, Any] = {
            **global_overrides,
            **dict(manips.get(conv.name, {})),
        }
        effective = conv.with_manipulations(conv_overrides) if conv_overrides else conv
        output = await ctx.runner.run(source=contents, conversion=effective)
        await ctx.disk.put(ctx.gen.path_for_conversion(media, conv.name), output)
        generated[conv.name] = True

        if conv.responsive_images_enabled:
            entry = await _generate_responsive_for_conversion(
                media, output, conv.name, disk=ctx.disk
            )
            if entry:
                responsive_updates[conv.name] = entry

    return generated, responsive_updates


async def _generate_responsive_for_conversion(
    media: Media,
    contents: bytes,
    conversion_name: str,
    *,
    disk: Any,
) -> dict[str, Any] | None:
    """Generate responsive variants from a conversion's output bytes."""
    from arvel_image.media.responsive_image_generator import (  # noqa: PLC0415
        generate_responsive_images_for_media,
    )

    return await generate_responsive_images_for_media(media, contents, conversion_name, disk=disk)


async def _maybe_regenerate_responsive(media: Media, contents: bytes, disk: Any) -> None:
    """Re-generate the original's responsive variants when they were previously generated.

    Only runs for the ``"medialibrary_original"`` group — conversion-level
    groups are handled inside ``_run_conversion_loop`` where the conversion
    output bytes are available.
    """
    if "medialibrary_original" not in (media.responsive_images or {}):
        return
    from arvel_image.media.responsive_image_generator import (  # noqa: PLC0415
        generate_responsive_images_for_media,
    )

    entry = await generate_responsive_images_for_media(
        media, contents, "medialibrary_original", disk=disk
    )
    if entry:
        existing = dict(media.responsive_images)
        existing["medialibrary_original"] = entry
        media.responsive_images = existing
