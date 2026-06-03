"""Queued image conversion job for arvel-image.

Run conversions asynchronously via the Arvel queue. Use
``FileAdder.queued()`` to dispatch one job per media upload instead of
running conversions inline.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from arvel.queue.job import Job
from pydantic import Field

from arvel_image.media.media_library import process_one as _process_one
from arvel_image.media.media_library import resolve_path_generator
from arvel_image.media.model import Media

if TYPE_CHECKING:
    from arvel_image.media.path_generator import PathGenerator


class QueuedConversionJob(Job):
    """Resolve a previously-uploaded :class:`Media` row and run its conversions.

    The host model class path is stored so the job can reload both the media
    row and its parent model at execution time — needed to access the
    collection's ``Conversion`` definitions.

    ``generate_responsive_images`` mirrors the FileAdder flag: when True the job
    generates srcset variants after conversions finish, keeping uploads fast.

    If the media row no longer exists (deleted before the job runs), the job
    exits silently. This is deliberate: the user may have removed the media
    between upload and processing.
    """

    queue: str = "media"
    tries: int = 3
    backoff: int | list[int] = Field(default_factory=lambda: [30, 60, 120])

    media_id: str
    # Full dotted path to the host model class, e.g. "app.models.product.Product"
    model_class_path: str
    generate_responsive_images: bool = False

    async def handle(self) -> None:
        media: Media | None = await Media.find(self.media_id)
        if media is None:
            return

        host = await _resolve_host(self.model_class_path, media.model_id)
        if host is None:
            return

        await _process_one(media, host)

        if self.generate_responsive_images and "medialibrary_original" not in (
            media.responsive_images or {}
        ):
            gen = resolve_path_generator()
            await _generate_responsive_for_job(media, gen)


async def _resolve_host(class_path: str, model_id: str) -> Any | None:
    """Dynamically load the host model instance from its class path and PK."""
    module_path, _, class_name = class_path.rpartition(".")
    if not module_path:
        return None
    try:
        module = importlib.import_module(module_path)
    except ImportError:
        return None
    cls = getattr(module, class_name, None)
    if cls is None:
        return None
    return await cls.find(model_id)


async def _generate_responsive_for_job(media: Media, gen: PathGenerator) -> None:
    """Generate fresh responsive variants for ``media`` at job execution time."""
    from arvel.facades.storage import Storage  # noqa: PLC0415

    from arvel_image.media.responsive_image_generator import (  # noqa: PLC0415
        generate_responsive_images_for_media,
    )

    disk_target: str | None = None if media.disk == "default" else media.disk
    disk = Storage.disk(disk_target)
    try:
        contents = await disk.get(gen.path_for(media))
    except Exception:  # noqa: BLE001
        return

    entry = await generate_responsive_images_for_media(
        media, contents, "medialibrary_original", disk=disk
    )
    if entry:
        existing = dict(media.responsive_images or {})
        existing["medialibrary_original"] = entry
        media.responsive_images = existing
        await media.save()


__all__ = ["QueuedConversionJob"]
