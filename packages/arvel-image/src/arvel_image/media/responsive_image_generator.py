"""Responsive image generation.

Width algorithm: file-size-optimized. Each step shrinks the width by
``sqrt(0.7)`` (≈0.8367); since file size scales roughly with area (w²),
that targets ~30% size reduction per step. Generation stops when the
predicted file size drops below 10 KB or the target width falls below 20 px.

``responsive_images`` column format (one key per generated group)::

    {
        "original": {
            "urls": [
                {"path": "1/responsive-images/photo___original_2400_1589.jpg",
                 "width": 2400, "height": 1589},
                ...
            ],
            "base64svg": "data:image/svg+xml;base64,..."
        }
    }

``"original"`` is the key for the original file's variants. Conversion-level
responsive groups use the conversion name as the key (e.g. ``"card"``).
"""

from __future__ import annotations

import base64
import math
from io import BytesIO
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Protocol, TypedDict, cast

import anyio.to_thread

if TYPE_CHECKING:
    from arvel.storage import StorageDisk

    from arvel_image.media.model import Media


class ResponsiveImageUrl(TypedDict):
    """One variant URL row in a ``ResponsiveImageEntry``."""

    path: str
    width: int
    height: int


class ResponsiveImageEntry(TypedDict):
    """One entry in the ``responsive_images`` JSON column.

    Keyed by group name in the parent dict — ``"original"`` for the original
    file's variants, conversion name (e.g. ``"card"``) for conversion-derived
    variants.
    """

    urls: list[ResponsiveImageUrl]
    base64svg: str


# Whole column shape: {group_key: ResponsiveImageEntry}. Functions that
# accept/return the full structure use this alias; row-level functions take
# the entry directly.
ResponsiveImages = dict[str, ResponsiveImageEntry]


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
    """Return widths (ascending, original included) for srcset variants.

    Each step shrinks the predicted file size by ~30% by shrinking the width
    by ``sqrt(0.7)``. The returned list is sorted ascending — srcset order is
    semantically unordered, but ascending is what humans and most static-site
    templating expects.
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
    widths.sort()
    return widths


def responsive_path(media: Media, width: int, height: int, key: str) -> str:
    """Disk-relative path for a responsive variant.

    Format: ``{id}/responsive-images/{stem}___{key}_{width}_{height}.{ext}``.
    """
    stem = PurePosixPath(media.file_name).stem
    ext = PurePosixPath(media.file_name).suffix.lstrip(".")
    return f"{media.id}/responsive-images/{stem}___{key}_{width}_{height}.{ext}"


def generate_placeholder_svg(source: bytes, width: int, height: int) -> str:
    """Return a ``data:image/svg+xml;base64,...`` placeholder URI.

    Creates a tiny (≤32 px) blurred JPEG thumbnail wrapped in an SVG
    ``<image>`` element, base64-encoded. Returns ``""`` on any error.
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
        # Placeholder is best-effort. Pillow can raise UnidentifiedImageError,
        # OSError, or codec quirks; an empty placeholder is fine — the rest
        # of the responsive entry still works.
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
    disk: StorageDisk,
) -> ResponsiveImageEntry | dict[str, Any]:
    """Generate all width variants, store them on ``disk``, return the column entry.

    Returns ``{}`` (an empty dict, not a valid entry) when the source is not a
    decodable image or is too small to generate any variants — caller should
    skip updating the column in that case. Successful returns are a fully
    populated :class:`ResponsiveImageEntry`.

    Pillow is CPU-bound; every decode/resize/encode is offloaded to a worker
    thread so this stays non-blocking when run inline during an upload.
    """
    dims = await anyio.to_thread.run_sync(_read_dimensions, source)
    if dims is None:
        return {}
    original_width, original_height, src_format = dims

    widths = calculate_responsive_widths(original_width, len(source))
    urls: list[ResponsiveImageUrl] = []

    for target_width in widths:
        variant = await anyio.to_thread.run_sync(
            _resize_variant, source, target_width, original_width, original_height, src_format
        )
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

    base64svg = await anyio.to_thread.run_sync(
        generate_placeholder_svg, source, original_width, original_height
    )
    return ResponsiveImageEntry(urls=urls, base64svg=base64svg)


def _read_dimensions(source: bytes) -> tuple[int, int, str] | None:
    """Return ``(width, height, format)`` for ``source``, or ``None`` if undecodable."""
    from PIL import Image as PILImage  # noqa: PLC0415

    try:
        with PILImage.open(BytesIO(source)) as img:
            width, height = img.size
            return width, height, img.format or "JPEG"
    except Exception:  # noqa: BLE001
        # Not a decodable image — caller skips the responsive entry. Pillow's
        # failure set is too wide (UnidentifiedImageError, OSError,
        # codec-specific errors) to narrow usefully.
        return None


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
        # A single variant failing is non-fatal — caller skips this width
        # and keeps the others. Pillow's failure set is too wide to narrow.
        return None


async def _put_quiet(disk: StorageDisk, path: str, data: bytes) -> bool:
    """Write ``data`` to ``path`` on ``disk``; return False on any error."""
    try:
        await disk.put(path, data)
    except Exception:  # noqa: BLE001
        # Storage drivers raise driver-specific errors (botocore, gcs, etc.) —
        # callers shouldn't have to depend on every backend's exception type
        # just to retry. Return-as-bool keeps the call site clean.
        return False
    else:
        return True


async def delete_responsive_images(
    responsive: dict[str, Any],
    *,
    disk: StorageDisk,
) -> None:
    """Best-effort delete all stored responsive variant files.

    Param is the loose JSON-column shape rather than :class:`ResponsiveImages`
    — older rows or hand-edited data may not match the strict schema exactly.
    The function defends with ``.get()`` rather than isinstance gates.
    """
    import contextlib  # noqa: PLC0415

    for entry in responsive.values():
        src_urls: list[Any] = entry.get("urls", []) or []
        for url_info in src_urls:
            path: str = url_info.get("path", "")
            if not path:
                continue
            with contextlib.suppress(Exception):
                await disk.delete(path)


async def _copy_variant(src_path: str, new_path: str, *, disk: StorageDisk) -> bool:
    """Copy a single responsive variant file. Returns False on any error."""
    try:
        contents = await disk.get(src_path)
        await disk.put(new_path, contents)
    except Exception:  # noqa: BLE001
        # Copy is best-effort: a missing source variant shouldn't abort the
        # row copy. Driver-specific exceptions are too wide to enumerate.
        return False
    else:
        return True


async def copy_responsive_images(
    src_responsive: dict[str, Any],
    new_media_id: int | str,
    *,
    disk: StorageDisk,
) -> ResponsiveImages:
    """Copy responsive variant files to a new media ID's path and return
    the rewritten ``responsive_images`` dict for the new row.

    Each ``path`` in ``src_responsive`` follows the format
    ``{src_id}/responsive-images/{filename}``. We copy the bytes to
    ``{new_media_id}/responsive-images/{filename}`` and rewrite paths in
    the returned dict. Files that fail to copy are silently skipped —
    the copy is best-effort so a missing variant doesn't abort the row copy.

    Param is the loose JSON-column shape; the return is the strict
    :class:`ResponsiveImages` (well-formed on the new row).
    """
    new_id_str = str(new_media_id)
    new_responsive: ResponsiveImages = {}

    for group_key, entry in src_responsive.items():
        src_urls: list[Any] = entry.get("urls", []) or []
        new_urls: list[ResponsiveImageUrl] = []

        for url_info in src_urls:
            src_path: str = url_info.get("path", "")
            if not src_path:
                continue
            # Replace leading "{src_id}/" with "{new_id}/"
            parts = src_path.split("/", 1)
            if len(parts) != 2:  # noqa: PLR2004
                continue
            new_path = f"{new_id_str}/{parts[1]}"
            if await _copy_variant(src_path, new_path, disk=disk):
                width = int(url_info.get("width", 0) or 0)
                height = int(url_info.get("height", 0) or 0)
                new_urls.append({"path": new_path, "width": width, "height": height})

        base64svg = entry.get("base64svg", "") or ""
        new_responsive[group_key] = {"urls": new_urls, "base64svg": base64svg}

    return new_responsive


__all__ = [
    "ResponsiveImageEntry",
    "ResponsiveImageUrl",
    "ResponsiveImages",
    "calculate_responsive_widths",
    "copy_responsive_images",
    "delete_responsive_images",
    "generate_placeholder_svg",
    "generate_responsive_images_for_media",
    "responsive_path",
]
