"""Synchronous conversion runner (with thread-pool offload).

: conversions run synchronously in v1, but the Pillow work is
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
        context: str | None = None,
    ) -> bytes:
        """Decode ``source``, apply ``conversion``, and return encoded bytes.

        ``context`` is an optional free-text tag (typically ``f"media id={m.id}"``)
        appended to the error message so callers don't have to wrap the
        exception just to add a row reference.

        Raises :class:`ConversionFailedError` (with the original error
        chained) on any failure during apply or encode.
        """
        try:
            return await anyio.to_thread.run_sync(
                self._apply_in_thread, source, conversion, context
            )
        except ConversionFailedError:
            raise
        except Exception as exc:
            # Broad on purpose: anyio surfaces thread-pool failures as the
            # original exception type, which varies (cancellation, Pillow,
            # OSError). Domain-wrap so callers only catch ConversionFailedError.
            raise ConversionFailedError(_format_error(conversion, source, context, exc)) from exc

    @staticmethod
    def _apply_in_thread(source: bytes, conversion: Conversion, context: str | None) -> bytes:
        try:
            image = Image.load(source)
            converted = conversion.apply(image)
            return converted.to_bytes()
        except Exception as exc:
            # Broad on purpose: Pillow + arvel_image.image can raise a wide
            # set (UnidentifiedImageError, UnsupportedFormatError, OSError,
            # ValueError); domain-wrap to keep the caller's catch list short.
            raise ConversionFailedError(_format_error(conversion, source, context, exc)) from exc


def _format_error(
    conversion: Conversion, source: bytes, context: str | None, exc: BaseException
) -> str:
    where = f" ({context})" if context else ""
    return f"Conversion {conversion.name!r} failed on a {len(source)}-byte source{where}: {exc}"


# Application-scoped accessor, mirroring path_generator and auth_service: an app
# overrides the runner (e.g. a queue-driven one) by calling set_conversion_runner
# in its own provider. None means "use the default ConversionRunner".
_custom_runner: ConversionRunner | None = None


def set_conversion_runner(runner: ConversionRunner) -> None:
    """Override the runner used by FileAdder, MediaLibrary, and queued jobs."""
    global _custom_runner  # noqa: PLW0603
    _custom_runner = runner


def get_conversion_runner() -> ConversionRunner:
    """Return the active conversion runner (custom or default)."""
    return _custom_runner if _custom_runner is not None else ConversionRunner()


__all__ = ["ConversionRunner", "get_conversion_runner", "set_conversion_runner"]
