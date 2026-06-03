"""MediaLibrary service for bulk operations"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel.database.orm.morph_map import get_morph_alias

if TYPE_CHECKING:
    from arvel_image.media.conversion_runner import ConversionRunner
    from arvel_image.media.model import Media
    from arvel_image.media.path_generator import PathGenerator
    from arvel_image.media.trait import HasMedia


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
        from arvel_image.media.conversion_runner import ConversionRunner  # noqa: PLC0415
        from arvel_image.media.model import Media  # noqa: PLC0415

        query = Media.query()
        if host is not None:
            query = query.where(Media.model_type == get_morph_alias(type(host)))
            query = query.where(Media.model_id == str(host.host_pk()))
        if collection is not None:
            query = query.where(Media.collection_name == collection)

        rows: list[Media] = list(await query.all())

        runner = ConversionRunner()
        gen = resolve_path_generator()
        processed = 0
        for media in rows:
            await process_one(media, host, runner, gen)
            processed += 1
        return processed


async def process_one(
    media: Media,
    host: HasMedia | None,
    runner: ConversionRunner,
    gen: PathGenerator,
) -> None:
    """Re-run conversions for a single media row. Skips quietly on errors."""
    from arvel.facades.storage import Storage  # noqa: PLC0415

    if not media.mime_type:
        return

    # read from media.disk regardless of whether host is supplied.
    read_disk_label = media.disk
    read_disk_target: str | None = None if read_disk_label == "default" else read_disk_label
    read_disk = Storage.disk(read_disk_target)

    try:
        contents = await read_disk.get(gen.path_for(media))
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

    generated: dict[str, Any] = {}
    for conv in coll.conversions:
        if not conv.accepts(media.mime_type):
            continue
        output = await runner.run(source=contents, conversion=conv)
        await write_disk.put(gen.path_for_conversion(media, conv.name), output)
        generated[conv.name] = True

    if generated:
        media.generated_conversions = {**(media.generated_conversions or {}), **generated}
        await media.save()
