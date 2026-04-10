"""ImageProcessor — Pillow-based image resize and compression engine."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

from arvel.media.exceptions import MediaProcessingError

if TYPE_CHECKING:
    from arvel.media.types import Conversion

_FIT_METHODS = {"cover", "contain", "fill", "inside", "outside"}

_FORMAT_FROM_MIME: dict[str, str] = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
    "image/gif": "GIF",
}

_MIME_FROM_FORMAT: dict[str, str] = {v: k for k, v in _FORMAT_FROM_MIME.items()}


def is_processable(mime_type: str) -> bool:
    """Return True if the MIME type is an image Pillow can process."""
    return mime_type in _FORMAT_FROM_MIME


class ImageProcessor:
    """Resize and compress images using Pillow.

    Requires ``pip install arvel[media]`` (Pillow>=12.2.0).
    """

    def __init__(
        self,
        *,
        quality: int = 85,
        output_format: str = "source",
    ) -> None:
        if quality < 1 or quality > 100:
            msg = f"quality must be 1-100, got {quality}"
            raise ValueError(msg)
        self._quality = quality
        self._output_format = output_format.upper() if output_format != "source" else "source"

    def process(
        self,
        file: bytes,
        conversion: Conversion,
        *,
        source_mime: str,
    ) -> tuple[bytes, str]:
        """Resize and compress *file* according to *conversion*.

        Returns ``(processed_bytes, output_mime_type)``.
        Raises ``MediaProcessingError`` if Pillow is not installed or processing fails.
        """
        try:
            from PIL import Image, ImageOps
        except ImportError:
            raise MediaProcessingError(
                "Pillow is required for image conversions. "
                "Install it with: pip install arvel[media]"
            ) from None

        source_format = _FORMAT_FROM_MIME.get(source_mime)
        if source_format is None:
            raise MediaProcessingError(f"Unsupported image MIME type: {source_mime}")

        try:
            img = Image.open(io.BytesIO(file))
        except Exception as exc:
            raise MediaProcessingError(f"Failed to open image: {exc}") from exc

        img = ImageOps.exif_transpose(img) or img

        target_size = (conversion.width, conversion.height)
        img = self._apply_fit(img, conversion.fit, target_size, ImageOps)

        out_format = self._resolve_format(source_format)
        out_mime = _MIME_FROM_FORMAT.get(out_format, source_mime)

        save_kwargs: dict[str, int | bool] = {}
        if out_format in ("JPEG", "WEBP"):
            save_kwargs["quality"] = self._quality
            save_kwargs["optimize"] = True
        elif out_format == "PNG":
            save_kwargs["optimize"] = True

        if out_format == "JPEG" and img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")

        buf = io.BytesIO()
        img.save(buf, format=out_format, **save_kwargs)
        return buf.getvalue(), out_mime

    @staticmethod
    def _apply_fit(img: Any, fit: str, target_size: tuple[int, int], image_ops: Any) -> Any:
        """Apply the fit/resize strategy and return the resized image."""
        if fit == "cover":
            return image_ops.fit(img, target_size)
        if fit == "contain" or fit in ("inside", "outside"):
            img.thumbnail(target_size)
            return img
        if fit == "fill":
            return img.resize(target_size)
        raise MediaProcessingError(f"Unknown fit mode: {fit}")

    def _resolve_format(self, source_format: str) -> str:
        if self._output_format == "source":
            return source_format
        return self._output_format
