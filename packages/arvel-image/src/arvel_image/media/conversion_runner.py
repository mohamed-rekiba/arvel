"""Synchronous conversion runner (with thread-pool offload).

ADR-082 D1: conversions run synchronously in v1, but the Pillow work is
CPU-bound, so we run it in a worker thread via ``anyio.to_thread.run_sync``.
That keeps the request loop responsive without dragging in a queue
backend on day one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio.to_thread

from arvel_image.image import Image
from arvel_image.media.exceptions import ConversionFailedError

if TYPE_CHECKING:
    from arvel_image.media.conversion import Conversion


class ConversionRunner:
    """Run a single :class:`Conversion` against raw source bytes."""

    async def run(
        self,
        *,
        source: bytes,
        conversion: Conversion,
    ) -> bytes:
        """Decode ``source``, apply ``conversion``, and return encoded bytes.

        Raises :class:`ConversionFailedError` (with the original error
        chained) on any failure during apply or encode.
        """
        try:
            return await anyio.to_thread.run_sync(self._apply_in_thread, source, conversion)
        except ConversionFailedError:
            raise
        except Exception as exc:
            msg = f"Conversion {conversion.name!r} failed: {exc}"
            raise ConversionFailedError(msg) from exc

    @staticmethod
    def _apply_in_thread(source: bytes, conversion: Conversion) -> bytes:
        try:
            image = Image.load(source)
            converted = conversion.apply(image)
            return converted.to_bytes()
        except Exception as exc:
            msg = f"Conversion {conversion.name!r} failed: {exc}"
            raise ConversionFailedError(msg) from exc


__all__ = ["ConversionRunner"]
