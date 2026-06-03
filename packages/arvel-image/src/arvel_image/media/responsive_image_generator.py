"""Responsive image generation — Spatie laravel-medialibrary v11 parity.

Width algorithm: FileSizeOptimizedWidthCalculator.
Each step: ``next_width = current_width * sqrt(0.7)`` (approx 0.8367).  Since
file size scales roughly as area (w^2), this targets ~30% reduction per step.
Generation stops when the predicted file size drops below 10 KB or the target
width falls below 20 px.

``responsive_images`` column format (one key per generated group)::

    {
        "medialibrary_original": {
            "urls": [
                {"path": "1/responsive-images/photo___medialibrary_original_2400_1589.jpg",
                 "width": 2400, "height": 1589},
                ...
            ],
            "base64svg": "data:image/svg+xml;base64,..."
        }
    }

``"medialibrary_original"`` is the key used for the original file's variants.
Conversion-level responsive images use the conversion name as the key.
"""

from __future__ import annotations

import base64
import math
from io import BytesIO
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Protocol, cast

if TYPE_CHECKING:
    from arvel_image.media.model import Media


class _PILImage(Protocol):
    """Minimal PIL Image interface for resize + save calls.

    The upstream stub types ``size`` as ``tuple[int, int] | list[int] | Unknown``
    which triggers ``reportUnknownMemberType``. This Protocol pins only the
    subset we use so pyright can reason about our code without touching the
    problematic stub union.
    """

    def resize(self, size: tuple[int, int], resample: int) -> _PILImage: ...
    def save(self, fp: Any, *args: Any, **kwargs: Any) -> None: ...

_MIN_WIDTH = 20
_MIN_FILE_SIZE = 10 * 1024  # 10 KB
_TINY_SIZE = 32  # thumbnail edge length for the SVG placeholder
_WIDTH_RATIO = math.sqrt(0.7)  # ≈ 0.8367


def calculate_responsive_widths(
    original_width: int,
    file_size: int,
) -> list[int]:
    """Return widths (largest first, original included) for srcset variants.

    Implements Spatie's FileSizeOptimizedWidthCalculator: each step reduces the
    predicted file size by ~30% by shrinking the width by sqrt(0.7).
    """
    widths: list[int] = [original_width]
    current = float(original_width)
    while True:
        current = current * _WIDTH_RATIO
        w = int(current)
        if w < _MIN_WIDTH:
            break
        est_size = int(file_size * (w / original_width) ** 2)
        if est_size < _MIN_FILE_SIZE:
            break
        widths.append(w)
    return widths


def responsive_path(media: Media, width: int, height: int, key: str) -> str:
    """Disk-relative path for a responsive variant.

    Format: ``{id}/responsive-images/{stem}___{key}_{width}_{height}.{ext}``
    Mirrors Spatie's ``ResponsiveImage`` filename scheme exactly.
    """
    stem = PurePosixPath(media.file_name).stem
    ext = PurePosixPath(media.file_name).suffix.lstrip(".")
    return f"{media.id}/responsive-images/{stem}___{key}_{width}_{height}.{ext}"


def generate_placeholder_svg(source: bytes, width: int, height: int) -> str:
    """Return a ``data:image/svg+xml;base64,...`` placeholder URI.

    Creates a tiny (≤32 px) blurred JPEG thumbnail wrapped in an SVG
    ``<image>`` element, base64-encoded, matching Spatie's
    ``TinyPlaceholderGenerator``. Returns ``""`` on any error.
    """
    from PIL import Image as PILImage  # noqa: PLC0415

    try:
        thumb_w = _TINY_SIZE
        thumb_h = max(1, int(_TINY_SIZE * height / width))
        with PILImage.open(BytesIO(source)) as img:
            converted = img.copy().convert("RGB")
        resized: _PILImage = cast("_PILImage", converted).resize(
            (thumb_w, thumb_h), PILImage.Resampling.LANCZOS
        )
        buf = BytesIO()
        resized.save(buf, format="JPEG", quality=20)
        img_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:  # noqa: BLE001
        return ""

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg"'
        f' xmlns:xlink="http://www.w3.org/1999/xlink"'
        f' viewBox="0 0 {width} {height}">'
        f'<filter id="b"><feGaussianBlur stdDeviation="3"/></filter>'
        f'<image width="{width}" height="{height}"'
        f' xlink:href="data:image/jpeg;base64,{img_b64}"'
        f' filter="url(#b)"/>'
        f"</svg>"
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode("ascii")


async def generate_responsive_images_for_media(
    media: Media,
    source: bytes,
    key: str,
    *,
    disk: Any,
) -> dict[str, Any]:
    """Generate all width variants, store them on ``disk``, return the column entry.

    Returns ``{}`` when the source is not a decodable image or is too small to
    generate any variants — caller should skip updating the column in that case.
    """
    from PIL import Image as PILImage  # noqa: PLC0415

    try:
        with PILImage.open(BytesIO(source)) as img:
            original_width, original_height = img.size
            src_format: str = img.format or "JPEG"
    except Exception:  # noqa: BLE001
        return {}

    widths = calculate_responsive_widths(original_width, len(source))
    urls: list[dict[str, Any]] = []

    for target_width in widths:
        variant = _resize_variant(source, target_width, original_width, original_height, src_format)
        if variant is None:
            continue
        variant_bytes, height = variant

        path = responsive_path(media, target_width, height, key)
        stored = await _put_quiet(disk, path, variant_bytes)
        if not stored:
            continue

        urls.append({"path": path, "width": target_width, "height": height})

    if not urls:
        return {}

    return {
        "urls": urls,
        "base64svg": generate_placeholder_svg(source, original_width, original_height),
    }


def _resize_variant(
    source: bytes,
    target_width: int,
    original_width: int,
    original_height: int,
    src_format: str,
) -> tuple[bytes, int] | None:
    """Return ``(bytes, height)`` for ``target_width``, or ``None`` on error."""
    from PIL import Image as PILImage  # noqa: PLC0415

    if target_width == original_width:
        return source, original_height

    ratio = target_width / original_width
    height = max(1, int(original_height * ratio))
    try:
        with PILImage.open(BytesIO(source)) as img:
            resized = cast("_PILImage", img.copy()).resize(
                (target_width, height), PILImage.Resampling.LANCZOS
            )
            buf = BytesIO()
            resized.save(buf, format=src_format)
            return buf.getvalue(), height
    except Exception:  # noqa: BLE001
        return None


async def _put_quiet(disk: Any, path: str, data: bytes) -> bool:
    """Write ``data`` to ``path`` on ``disk``; return False on any error."""
    try:
        await disk.put(path, data)
    except Exception:  # noqa: BLE001
        return False
    else:
        return True


async def delete_responsive_images(
    responsive: dict[str, Any],
    *,
    disk: Any,
) -> None:
    """Best-effort delete all stored responsive variant files."""
    import contextlib  # noqa: PLC0415

    for entry in responsive.values():
        for url_info in entry.get("urls", []):
            path: str = url_info.get("path", "")
            if not path:
                continue
            with contextlib.suppress(Exception):
                await disk.delete(path)


__all__ = [
    "calculate_responsive_widths",
    "delete_responsive_images",
    "generate_placeholder_svg",
    "generate_responsive_images_for_media",
    "responsive_path",
]
