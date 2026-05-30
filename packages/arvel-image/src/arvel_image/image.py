"""Chainable image manipulations (Spatie Image parity, Pillow-only).

Public surface:

- :class:`Image` — fluent wrapper around a Pillow ``Image``.
- :class:`UnsupportedFormatError` — raised when ``.format()`` is given an
  unsupported format. The allowed set is intentionally narrow (jpeg/jpg/png/
  webp/gif) — if you need TIFF or BMP, drop down to Pillow directly.

The whole class is synchronous. Pillow is CPU-bound; image manipulation in
request handlers should be wrapped in ``run_in_threadpool`` (Starlette/FastAPI)
or ``asyncio.to_thread``.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import IO, Protocol, Self, cast

from PIL import Image as PILImage
from PIL import ImageOps


class _Resizable(Protocol):
    """Narrowed PIL ``resize`` signature without numpy unions in the type."""

    def resize(self, size: tuple[int, int], resample: int) -> PILImage.Image: ...


_SUPPORTED_FORMATS: dict[str, str] = {
    "jpeg": "JPEG",
    "jpg": "JPEG",
    "png": "PNG",
    "webp": "WEBP",
    "gif": "GIF",
}

_FitMode = str  # "cover" | "contain"

_MIN_QUALITY = 1
_MAX_QUALITY = 100


class UnsupportedFormatError(ValueError):
    """Raised when an unsupported output format is requested."""


def _normalize_format(fmt: str) -> str:
    key = fmt.strip().lower()
    if key not in _SUPPORTED_FORMATS:
        raise UnsupportedFormatError(
            f"Format '{fmt}' is not supported. Supported: {sorted(_SUPPORTED_FORMATS.keys())}"
        )
    return _SUPPORTED_FORMATS[key]


class Image:
    """Fluent wrapper around a Pillow image. Chain operations, terminate with
    :meth:`to_bytes` or :meth:`save`.
    """

    def __init__(self, pil_image: PILImage.Image) -> None:
        self._image = pil_image
        self._format: str | None = pil_image.format
        self._quality: int | None = None

    @classmethod
    def load(cls, source: str | Path | IO[bytes] | bytes) -> Self:
        """Open an image from a path, bytes, or a binary file-like object.

        The underlying file is read fully and decoded eagerly so callers can
        close the source without losing pixels.
        """
        if isinstance(source, (str, Path)):
            with PILImage.open(source) as opened:
                opened.load()
                return cls(opened.copy())
        if isinstance(source, bytes):
            with PILImage.open(BytesIO(source)) as opened:
                opened.load()
                return cls(opened.copy())
        with PILImage.open(source) as opened:
            opened.load()
            return cls(opened.copy())

    @property
    def width(self) -> int:
        return self._image.width

    @property
    def height(self) -> int:
        return self._image.height

    def resize(self, *, width: int, height: int) -> Self:
        """Stretch the image to the exact (width, height) box."""
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be positive")
        resizable = cast("_Resizable", self._image)
        self._image = resizable.resize((width, height), PILImage.Resampling.LANCZOS)
        return self

    def fit(self, mode: _FitMode, width: int, height: int) -> Self:
        """Fit into ``(width, height)``.

        - ``cover``: crop to fill the target box exactly.
        - ``contain``: scale to fit inside the target box, preserving aspect.
        """
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be positive")
        if mode == "cover":
            fitted = ImageOps.fit(self._image, (width, height), method=PILImage.Resampling.LANCZOS)
        elif mode == "contain":
            copy = self._image.copy()
            copy.thumbnail((width, height), PILImage.Resampling.LANCZOS)
            fitted = copy
        else:
            raise ValueError(f"Unknown fit mode '{mode}'. Use 'cover' or 'contain'.")
        self._image = fitted
        return self

    def crop(self, *, left: int, top: int, width: int, height: int) -> Self:
        box = (left, top, left + width, top + height)
        self._image = self._image.crop(box)
        return self

    def quality(self, value: int) -> Self:
        if not _MIN_QUALITY <= value <= _MAX_QUALITY:
            raise ValueError(f"quality must be between {_MIN_QUALITY} and {_MAX_QUALITY} inclusive")
        self._quality = value
        return self

    def format(self, image_format: str) -> Self:
        self._format = _normalize_format(image_format)
        return self

    def optimize(self) -> Self:
        """Strip EXIF metadata and re-encode at current quality settings (FR-046-16).

        Privacy default: EXIF is removed from JPEG output. Non-JPEG images are
        left structurally unchanged (PNG has no EXIF standard slot).
        """
        # Auto-orient then strip EXIF by re-encoding without the exif kwarg.
        self._image = ImageOps.exif_transpose(self._image) or self._image
        return self

    def to_bytes(self, image_format: str | None = None) -> bytes:
        """Serialize the image to bytes using the chosen format (or current)."""
        target = _normalize_format(image_format) if image_format else (self._format or "PNG")
        buffer = BytesIO()
        kwargs = self._save_kwargs(target)
        self._encode_for_target(target).save(buffer, format=target, **kwargs)
        return buffer.getvalue()

    def save(self, path: str | Path, *, image_format: str | None = None) -> Self:
        """Persist to disk. Format is taken from ``image_format``, then
        :meth:`format`, then the file extension, then PNG.
        """
        if image_format is not None:
            target = _normalize_format(image_format)
        elif self._format and self._format != "MPO":
            target = self._format
        else:
            target = _normalize_format(Path(path).suffix.lstrip(".") or "png")
        kwargs = self._save_kwargs(target)
        self._encode_for_target(target).save(path, format=target, **kwargs)
        return self

    def _save_kwargs(self, target: str) -> dict[str, object]:
        kwargs: dict[str, object] = {}
        if self._quality is not None and target in {"JPEG", "WEBP"}:
            kwargs["quality"] = self._quality
        return kwargs

    def _encode_for_target(self, target: str) -> PILImage.Image:
        """Convert the working image to a mode the target encoder accepts.

        JPEG cannot encode alpha — composite RGBA over white before saving.
        Other formats pass through.
        """
        if target == "JPEG" and self._image.mode in {"RGBA", "LA", "P"}:
            converted = self._image.convert("RGBA")
            background = PILImage.new("RGB", converted.size, (255, 255, 255))
            background.paste(converted, mask=converted.split()[-1])
            return background
        return self._image

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<Image {self.width}x{self.height} format={self._format}>"
