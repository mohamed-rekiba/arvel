"""Chainable image manipulations, Pillow-only.

Public surface:

- :class:`Image` — fluent wrapper around a Pillow ``Image``.
- :class:`UnsupportedFormatError` — raised when ``.format()`` is given an
  unsupported format. The allowed set is intentionally narrow (jpeg/jpg/png/
  webp/gif) — if you need TIFF or BMP, drop down to Pillow directly.

The chain is lazy: ``load`` and the pixel operations (``resize``, ``fit``,
``crop``, ``optimize``) record what to do; nothing decodes or transforms until
a terminal (:meth:`to_bytes` / :meth:`save`) runs. Argument validation
(``quality`` range, ``format`` support, positive dimensions) still happens
eagerly at call time so mistakes fail fast.

Pillow is CPU-bound. The sync terminals run inline; the ``*_async`` terminals
offload the *whole* pipeline — decode, transforms, encode — to a worker thread
so they don't block the event loop in an async handler.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import IO, Protocol, Self, cast

from PIL import Image as PILImage
from PIL import ImageOps


class _Resizable(Protocol):
    """Narrowed PIL ``resize`` signature without numpy unions in the type."""

    def resize(self, size: tuple[int, int], resample: int) -> PILImage.Image: ...


_Source = Callable[[], PILImage.Image]
_PixelOp = Callable[[PILImage.Image], PILImage.Image]

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


def _decode_path(path: str | Path) -> PILImage.Image:
    with PILImage.open(path) as opened:
        opened.load()
        return opened.copy()


def _decode_bytes(data: bytes) -> PILImage.Image:
    with PILImage.open(BytesIO(data)) as opened:
        opened.load()
        return opened.copy()


class Image:
    """Fluent wrapper around a Pillow image. Chain operations, terminate with
    :meth:`to_bytes` / :meth:`to_bytes_async` or :meth:`save` / :meth:`save_async`.

    Building is deferred and side-effect free, so an instance is reusable —
    calling a terminal twice decodes and replays the chain each time rather
    than mutating shared state.
    """

    def __init__(self, source: _Source) -> None:
        self._source = source
        self._ops: list[_PixelOp] = []
        self._explicit_format: str | None = None
        self._quality: int | None = None
        self._strip_exif: bool = False

    @classmethod
    def load(cls, source: str | Path | IO[bytes] | bytes) -> Self:
        """Open an image from a path, bytes, or a binary file-like object.

        Paths and bytes decode lazily at the terminal. File-like sources are
        read into memory now (they may be closed before the terminal runs),
        but decoding is still deferred.
        """
        if isinstance(source, (str, Path)):
            path = source
            return cls(lambda: _decode_path(path))
        if isinstance(source, bytes):
            data = source
            return cls(lambda: _decode_bytes(data))
        snapshot = source.read()
        return cls(lambda: _decode_bytes(snapshot))

    @property
    def width(self) -> int:
        """Width after replaying the chain. Forces a decode."""
        return self.build().width

    @property
    def height(self) -> int:
        """Height after replaying the chain. Forces a decode."""
        return self.build().height

    def resize(self, *, width: int, height: int) -> Self:
        """Stretch the image to the exact (width, height) box."""
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be positive")

        def _op(image: PILImage.Image) -> PILImage.Image:
            resizable = cast("_Resizable", image)
            return resizable.resize((width, height), PILImage.Resampling.LANCZOS)

        self._ops.append(_op)
        return self

    def to_width(self, pixels: int) -> Self:
        """Resize to exact ``pixels`` width, preserving aspect ratio."""
        if pixels <= 0:
            raise ValueError("width must be positive")

        def _op(image: PILImage.Image) -> PILImage.Image:
            target_height = max(1, round(image.height * pixels / image.width))
            resizable = cast("_Resizable", image)
            return resizable.resize((pixels, target_height), PILImage.Resampling.LANCZOS)

        self._ops.append(_op)
        return self

    def to_height(self, pixels: int) -> Self:
        """Resize to exact ``pixels`` height, preserving aspect ratio."""
        if pixels <= 0:
            raise ValueError("height must be positive")

        def _op(image: PILImage.Image) -> PILImage.Image:
            target_width = max(1, round(image.width * pixels / image.height))
            resizable = cast("_Resizable", image)
            return resizable.resize((target_width, pixels), PILImage.Resampling.LANCZOS)

        self._ops.append(_op)
        return self

    def fit(self, mode: _FitMode, width: int, height: int) -> Self:
        """Fit into ``(width, height)``.

        - ``cover``: crop to fill the target box exactly.
        - ``contain``: scale to fit inside the target box, preserving aspect.
        """
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be positive")
        if mode not in {"cover", "contain"}:
            raise ValueError(f"Unknown fit mode '{mode}'. Use 'cover' or 'contain'.")

        def _op(image: PILImage.Image) -> PILImage.Image:
            if mode == "cover":
                return ImageOps.fit(image, (width, height), method=PILImage.Resampling.LANCZOS)
            copy = image.copy()
            copy.thumbnail((width, height), PILImage.Resampling.LANCZOS)
            return copy

        self._ops.append(_op)
        return self

    def crop(self, *, left: int, top: int, width: int, height: int) -> Self:
        box = (left, top, left + width, top + height)
        self._ops.append(lambda image: image.crop(box))
        return self

    def quality(self, value: int) -> Self:
        if not _MIN_QUALITY <= value <= _MAX_QUALITY:
            raise ValueError(f"quality must be between {_MIN_QUALITY} and {_MAX_QUALITY} inclusive")
        self._quality = value
        return self

    def format(self, image_format: str) -> Self:
        self._explicit_format = _normalize_format(image_format)
        return self

    def strip_exif(self) -> Self:
        """Explicitly zero out all EXIF/XMP metadata before encoding.

        Every re-encode already drops the raw EXIF block (Pillow doesn't copy
        it forward). Call ``strip_exif()`` when you need the guarantee at the
        API level — e.g. user-uploaded photos where GPS removal is a stated
        privacy requirement. Safe to combine with ``optimize()``.
        """
        self._strip_exif = True
        return self

    def optimize(self) -> Self:
        """Bake EXIF orientation into the pixels via ``exif_transpose``.

        The terminals never copy the source EXIF block forward, so every
        re-encode already drops EXIF (GPS included). This op exists so that
        orientation survives that drop — without it, a rotated photo would
        re-encode upright-tag-less and display sideways.
        """
        self._ops.append(lambda image: ImageOps.exif_transpose(image) or image)
        return self

    def to_bytes(self, image_format: str | None = None) -> bytes:
        """Serialize the image to bytes using the chosen format (or current)."""
        image = self.build()
        target = self._resolve_to_bytes_target(image, image_format)
        buffer = BytesIO()
        kwargs = self.save_kwargs(target)
        self._encode_for_target(image, target).save(buffer, format=target, **kwargs)
        return buffer.getvalue()

    async def to_bytes_async(self, image_format: str | None = None) -> bytes:
        """Offload the whole pipeline (decode + transforms + encode) to a thread."""
        return await asyncio.to_thread(self.to_bytes, image_format)

    def save(self, path: str | Path, *, image_format: str | None = None) -> Self:
        """Persist to disk. Format is taken from ``image_format``, then
        :meth:`format`, then the source format, then the file extension, then PNG.
        """
        image = self.build()
        target = self._resolve_save_target(image, path, image_format)
        kwargs = self.save_kwargs(target)
        self._encode_for_target(image, target).save(path, format=target, **kwargs)
        return self

    async def save_async(self, path: str | Path, *, image_format: str | None = None) -> Self:
        """Offload the whole pipeline (decode + transforms + encode) to a thread."""
        return await asyncio.to_thread(self.save, path, image_format=image_format)

    def build(self) -> PILImage.Image:
        """Decode the source and replay the recorded pixel ops, fresh each call."""
        image = self._source()
        for op in self._ops:
            image = op(image)
        if self._strip_exif:
            image.info.pop("exif", None)
            image.info.pop("xmp", None)
        return image

    def _resolve_to_bytes_target(self, image: PILImage.Image, image_format: str | None) -> str:
        if image_format is not None:
            return _normalize_format(image_format)
        return self._explicit_format or image.format or "PNG"

    def _resolve_save_target(
        self, image: PILImage.Image, path: str | Path, image_format: str | None
    ) -> str:
        if image_format is not None:
            return _normalize_format(image_format)
        if self._explicit_format is not None:
            return self._explicit_format
        if image.format and image.format != "MPO":
            return image.format
        return _normalize_format(Path(path).suffix.lstrip(".") or "png")

    def save_kwargs(self, target: str) -> dict[str, object]:
        kwargs: dict[str, object] = {}
        if self._quality is not None and target in {"JPEG", "WEBP"}:
            kwargs["quality"] = self._quality
        if self._strip_exif and target in {"JPEG", "WEBP", "PNG"}:
            kwargs["exif"] = b""
        return kwargs

    def _encode_for_target(self, image: PILImage.Image, target: str) -> PILImage.Image:
        """Convert the working image to a mode the target encoder accepts.

        JPEG cannot encode alpha — composite RGBA over white before saving.
        Other formats pass through.
        """
        if target == "JPEG" and image.mode in {"RGBA", "LA", "P"}:
            converted = image.convert("RGBA")
            background = PILImage.new("RGB", converted.size, (255, 255, 255))
            background.paste(converted, mask=converted.split()[-1])
            return background
        return image

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<Image ops={len(self._ops)} format={self._explicit_format}>"
