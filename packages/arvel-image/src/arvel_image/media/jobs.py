"""Queued image conversion job for arvel-image.

Run conversions asynchronously via the Arvel queue. Use
``FileAdder.queued()`` to dispatch one job per media upload instead of
running conversions inline.
"""

from __future__ import annotations

import importlib
from typing import Any

from arvel.queue.job import Job
from pydantic import Field

from arvel_image.media.conversion_runner import get_conversion_runner
from arvel_image.media.media_library import process_one as _process_one
from arvel_image.media.media_library import resolve_path_generator
from arvel_image.media.model import Media


class QueuedConversionJob(Job):
    """Resolve a previously-uploaded :class:`Media` row and run its conversions.

    The host model class path is stored so the job can reload both the media
    row and its parent model at execution time — needed to access the
    collection's ``Conversion`` definitions.

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

    async def handle(self) -> None:
        media: Media | None = await Media.find(self.media_id)
        if media is None:
            return

        host = await _resolve_host(self.model_class_path, media.model_id)
        if host is None:
            return

        runner = get_conversion_runner()
        gen = resolve_path_generator()
        await _process_one(media, host, runner, gen)


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


__all__ = ["QueuedConversionJob"]
