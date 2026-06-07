"""Branch coverage for responsive_image_generator.py.

Pins the missing branches surfaced by the coverage report. Each test names the
branch it covers so the link from coverage gap to test is visible.

Fakes are minimal — they implement the StorageDisk Protocol just enough for
the function under test. No SQLAlchemy, no host model — these are unit tests
against the module-level functions.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from typing import Any, BinaryIO

import pytest

pytest.importorskip("PIL", reason="arvel-image depends on Pillow")

from arvel_image.media.responsive_image_generator import (
    copy_responsive_images,
    delete_responsive_images,
    generate_responsive_images_for_media,
)

# ─── Fakes ───────────────────────────────────────────────────────────────────


# Signature of the module-internal `_resize_variant` helper — referenced from
# the resize-failure test below via getattr (private cross-module access).
type _ResizeFn = Callable[[bytes, int, int, int, str], tuple[bytes, int] | None]


class _InMemoryDisk:
    """StorageDisk fake — keeps bytes in a dict; tracks delete calls."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def exists(self, path: str) -> bool:
        return path in self.files

    async def get(self, path: str) -> bytes:
        return self.files[path]

    async def put(self, path: str, contents: bytes | str | BinaryIO) -> bool:
        if isinstance(contents, (bytes, bytearray)):
            self.files[path] = bytes(contents)
        elif isinstance(contents, str):
            self.files[path] = contents.encode()
        else:
            self.files[path] = contents.read()
        return True

    async def delete(self, path: str) -> bool:
        self.deleted.append(path)
        self.files.pop(path, None)
        return True

    async def list(self, directory: str = "") -> list[str]:
        return [p for p in self.files if p.startswith(directory)]

    def url(self, path: str) -> str:
        return f"memory://{path}"

    def temporary_url(self, path: str, expiry: int) -> str:
        return f"memory://{path}?expires={expiry}"


class _RaisingPutDisk(_InMemoryDisk):
    """Fake that raises on put — pins the _put_quiet exception branch."""

    async def put(self, path: str, contents: bytes | str | BinaryIO) -> bool:
        msg = "simulated storage failure"
        raise OSError(msg)


class _RaisingGetDisk(_InMemoryDisk):
    """Fake that raises on get — pins the _copy_variant exception branch."""

    async def get(self, path: str) -> bytes:
        msg = "source variant missing"
        raise OSError(msg)


class _RaisingDeleteDisk(_InMemoryDisk):
    """Fake that raises on delete — pins delete_responsive_images suppression."""

    async def delete(self, path: str) -> bool:
        msg = "delete failed"
        raise OSError(msg)


class _FakeMedia:
    """Minimal Media stand-in — only the attributes responsive_path() reads."""

    def __init__(self, media_id: int = 42, file_name: str = "photo.jpg") -> None:
        self.id = media_id
        self.file_name = file_name


def _jpeg(width: int, height: int) -> bytes:
    from PIL import Image as PILImage

    buf = io.BytesIO()
    PILImage.new("RGB", (width, height), (100, 150, 200)).save(buf, format="JPEG", quality=85)
    return buf.getvalue()


# ─── main entry rejection paths ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_corrupt_source_returns_empty_dict() -> None:
    # L178-182: Pillow can't decode → except Exception → return {}
    disk = _InMemoryDisk()
    media = _FakeMedia()
    result = await generate_responsive_images_for_media(
        media,  # type: ignore[arg-type]
        b"this is not a real image",
        "original",
        disk=disk,
    )
    assert result == {}
    assert disk.files == {}, "no bytes should have been written when decode failed"


@pytest.mark.asyncio
async def test_truncated_jpeg_header_returns_empty_dict() -> None:
    # Same L178-182 branch via a different corrupt-source shape (JPEG SOI only)
    disk = _InMemoryDisk()
    media = _FakeMedia()
    result = await generate_responsive_images_for_media(
        media,  # type: ignore[arg-type]
        b"\xff\xd8",  # JPEG start-of-image with nothing after
        "original",
        disk=disk,
    )
    assert result == {}


@pytest.mark.asyncio
async def test_empty_widths_returns_empty_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # L201: the `if not urls: return {}` early exit.
    # calculate_responsive_widths always includes the original width — there's
    # no realistic input that yields an empty list. We force it via monkeypatch
    # to pin the L201 branch directly.
    import arvel_image.media.responsive_image_generator as gen

    disk = _InMemoryDisk()
    media = _FakeMedia()

    def _no_widths(_w: int, _f: int) -> list[int]:
        return []

    monkeypatch.setattr(gen, "calculate_responsive_widths", _no_widths)
    result = await generate_responsive_images_for_media(
        media,  # type: ignore[arg-type]
        _jpeg(100, 100),
        "original",
        disk=disk,
    )
    assert result == {}
    assert disk.files == {}


# ─── per-width skip paths ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_storage_put_failure_skips_width(monkeypatch: pytest.MonkeyPatch) -> None:
    # L196: _put_quiet returns False → `if not stored: continue` skips this width.
    # L242-246: _put_quiet exception branch (OSError caught, returns False).
    disk = _RaisingPutDisk()
    media = _FakeMedia()
    source = _jpeg(800, 600)
    result = await generate_responsive_images_for_media(
        media,  # type: ignore[arg-type]
        source,
        "original",
        disk=disk,
    )
    # Every width's put() raised → every width skipped → no urls collected → return {}
    assert result == {}, "all writes failed; entry should be empty"


@pytest.mark.asyncio
async def test_resize_failure_skips_width(monkeypatch: pytest.MonkeyPatch) -> None:
    # L190: _resize_variant returns None → `if variant is None: continue`.
    # L222-235: _resize_variant exception branch (Pillow raises during resize).
    import arvel_image.media.responsive_image_generator as gen

    disk = _InMemoryDisk()
    media = _FakeMedia()
    source = _jpeg(800, 600)

    # Patch _resize_variant to fail for every non-original width, succeed for original.
    # getattr/setattr bypass pyright's reportPrivateUsage — exactly the kind of
    # cross-module internal reach a unit test needs to make.
    original_resize: _ResizeFn = getattr(gen, "_resize_variant")  # noqa: B009
    call_count = {"n": 0}

    def _fail_after_first(
        src: bytes, target_w: int, orig_w: int, orig_h: int, fmt: str
    ) -> tuple[bytes, int] | None:
        call_count["n"] += 1
        if target_w == orig_w:
            return original_resize(src, target_w, orig_w, orig_h, fmt)
        return None  # simulate resize failure

    monkeypatch.setattr(gen, "_resize_variant", _fail_after_first)

    result = await generate_responsive_images_for_media(
        media,  # type: ignore[arg-type]
        source,
        "original",
        disk=disk,
    )
    # Only the original-width variant survives — that's enough to pass the
    # `if not urls: return {}` gate.
    assert result != {}
    assert "urls" in result
    assert len(result["urls"]) == 1, "only the original-width variant should survive"
    assert result["urls"][0]["width"] == 800


@pytest.mark.asyncio
async def test_resize_exception_propagates_as_none_then_continue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # L222-235: _resize_variant's `try/except Exception` branch returns None on
    # any Pillow failure. Verified by patching PILImage.open inside the helper
    # to raise.
    from PIL import Image as PILImage

    disk = _InMemoryDisk()
    media = _FakeMedia()
    source = _jpeg(800, 600)

    # Patch PILImage.open globally — first call succeeds (main entry decodes
    # original dimensions), then subsequent calls (inside _resize_variant) raise.
    real_open = PILImage.open
    call_count = {"n": 0}

    def _open_then_raise(*args: Any, **kwargs: Any) -> Any:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return real_open(*args, **kwargs)
        msg = "simulated Pillow failure during resize"
        raise OSError(msg)

    monkeypatch.setattr(PILImage, "open", _open_then_raise)

    result = await generate_responsive_images_for_media(
        media,  # type: ignore[arg-type]
        source,
        "original",
        disk=disk,
    )
    # The original-width variant doesn't go through PILImage.open (early return
    # path), so it survives. Everything else fails and gets skipped.
    assert "urls" in result
    assert all(u["width"] == 800 for u in result["urls"])


# ─── _copy_variant exception branch ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_copy_skips_variant_when_source_missing() -> None:
    # L279-282: _copy_variant's exception branch (OSError on get → return False).
    disk = _RaisingGetDisk()
    big_path = "1/responsive-images/photo___original_800_600.jpg"
    small_path = "1/responsive-images/photo___original_400_300.jpg"
    src_responsive: dict[str, Any] = {
        "original": {
            "urls": [
                {"path": big_path, "width": 800, "height": 600},
                {"path": small_path, "width": 400, "height": 300},
            ],
            "base64svg": "data:image/svg+xml;base64,abc",
        }
    }
    result = await copy_responsive_images(src_responsive, new_media_id=2, disk=disk)
    # All gets raised → all copies failed → new_urls empty for the group, but
    # the group itself is still recorded (with empty urls) — that's the contract.
    assert "original" in result
    assert result["original"]["urls"] == []
    assert result["original"]["base64svg"] == "data:image/svg+xml;base64,abc"


@pytest.mark.asyncio
async def test_copy_variant_happy_path_writes_to_new_path() -> None:
    # Positive control — exercises _copy_variant's success branch (L274-278, 284).
    disk = _InMemoryDisk()
    src_path = "1/responsive-images/photo___original_800_600.jpg"
    disk.files[src_path] = b"fake-image-bytes"

    src_responsive: dict[str, Any] = {
        "original": {
            "urls": [
                {"path": src_path, "width": 800, "height": 600},
            ],
            "base64svg": "data:image/svg+xml;base64,xyz",
        }
    }
    result = await copy_responsive_images(src_responsive, new_media_id=2, disk=disk)
    assert "original" in result
    assert len(result["original"]["urls"]) == 1
    new_url = result["original"]["urls"][0]
    assert new_url["path"] == "2/responsive-images/photo___original_800_600.jpg"
    assert new_url["width"] == 800
    assert new_url["height"] == 600
    assert disk.files[new_url["path"]] == b"fake-image-bytes"


# ─── delete_responsive_images defensive paths ────────────────────────────────


@pytest.mark.asyncio
async def test_delete_happy_path_removes_all_variants() -> None:
    # L264-271: main loop — entries with urls + paths get deleted.
    disk = _InMemoryDisk()
    disk.files = {
        "1/responsive-images/a.jpg": b"a",
        "1/responsive-images/b.jpg": b"b",
    }
    responsive: dict[str, Any] = {
        "original": {
            "urls": [
                {"path": "1/responsive-images/a.jpg", "width": 800, "height": 600},
                {"path": "1/responsive-images/b.jpg", "width": 400, "height": 300},
            ],
            "base64svg": "",
        }
    }
    await delete_responsive_images(responsive, disk=disk)
    assert "1/responsive-images/a.jpg" in disk.deleted
    assert "1/responsive-images/b.jpg" in disk.deleted


@pytest.mark.asyncio
async def test_delete_skips_empty_path_entries() -> None:
    # L267-269: `path: str = url_info.get("path", "")` + `if not path: continue`.
    disk = _InMemoryDisk()
    responsive: dict[str, Any] = {
        "original": {
            "urls": [
                {"path": "", "width": 800, "height": 600},  # empty path → skip
                {"width": 400, "height": 300},  # missing path key → "" → skip
            ],
            "base64svg": "",
        }
    }
    await delete_responsive_images(responsive, disk=disk)
    assert disk.deleted == [], "empty-path entries must not call disk.delete"


@pytest.mark.asyncio
async def test_delete_handles_missing_or_none_urls_key() -> None:
    # L265: `src_urls: list[Any] = entry.get("urls", []) or []`
    # Defensive against hand-edited rows where urls is missing or null.
    disk = _InMemoryDisk()
    responsive: dict[str, Any] = {
        "original": {"base64svg": "..."},  # no urls key at all
        "card": {"urls": None, "base64svg": "..."},  # urls is None
    }
    await delete_responsive_images(responsive, disk=disk)
    assert disk.deleted == []


@pytest.mark.asyncio
async def test_delete_suppresses_disk_errors() -> None:
    # L270-271: `with contextlib.suppress(Exception): await disk.delete(path)`.
    disk = _RaisingDeleteDisk()
    responsive: dict[str, Any] = {
        "original": {
            "urls": [
                {"path": "1/responsive-images/a.jpg", "width": 800, "height": 600},
            ],
            "base64svg": "",
        }
    }
    # Must not raise — the suppress() wraps the delete call.
    await delete_responsive_images(responsive, disk=disk)


# ─── copy_responsive_images defensive paths ──────────────────────────────────


@pytest.mark.asyncio
async def test_copy_skips_url_with_empty_path() -> None:
    # L314-315: `if not src_path: continue`
    disk = _InMemoryDisk()
    src_responsive: dict[str, Any] = {
        "original": {
            "urls": [{"path": "", "width": 800, "height": 600}],
            "base64svg": "",
        }
    }
    result = await copy_responsive_images(src_responsive, new_media_id=2, disk=disk)
    assert result["original"]["urls"] == []


@pytest.mark.asyncio
async def test_copy_skips_url_with_malformed_path() -> None:
    # L317-319: `parts = src_path.split("/", 1)`; `if len(parts) != 2: continue`
    # A path with no "/" can't be rewritten — must be skipped.
    disk = _InMemoryDisk()
    src_responsive: dict[str, Any] = {
        "original": {
            "urls": [{"path": "no-slash-here.jpg", "width": 800, "height": 600}],
            "base64svg": "",
        }
    }
    result = await copy_responsive_images(src_responsive, new_media_id=2, disk=disk)
    assert result["original"]["urls"] == []


# ─── Edge: empty/None urls in copy (parallel to delete defensive paths) ──────


@pytest.mark.asyncio
async def test_copy_handles_missing_urls_key() -> None:
    # L309: `src_urls: list[Any] = entry.get("urls", []) or []`
    disk = _InMemoryDisk()
    src_responsive: dict[str, Any] = {
        "original": {"base64svg": "svg-data"},
        "card": {"urls": None, "base64svg": ""},
    }
    result = await copy_responsive_images(src_responsive, new_media_id=2, disk=disk)
    assert result["original"]["urls"] == []
    assert result["original"]["base64svg"] == "svg-data"
    assert result["card"]["urls"] == []


@pytest.mark.asyncio
async def test_copy_preserves_base64svg_when_present() -> None:
    # L326: `base64svg = entry.get("base64svg", "") or ""`
    disk = _InMemoryDisk()
    disk.files["1/responsive-images/a.jpg"] = b"bytes"
    src_responsive: dict[str, Any] = {
        "original": {
            "urls": [{"path": "1/responsive-images/a.jpg", "width": 800, "height": 600}],
            "base64svg": "data:image/svg+xml;base64,XYZ",
        }
    }
    result = await copy_responsive_images(src_responsive, new_media_id=99, disk=disk)
    assert result["original"]["base64svg"] == "data:image/svg+xml;base64,XYZ"


@pytest.mark.asyncio
async def test_copy_defaults_missing_base64svg_to_empty_string() -> None:
    # L326 fallback when base64svg key is absent.
    disk = _InMemoryDisk()
    src_responsive: dict[str, Any] = {
        "original": {
            "urls": [],
        }
    }
    result = await copy_responsive_images(src_responsive, new_media_id=99, disk=disk)
    assert result["original"]["base64svg"] == ""


# ─── defensive width/height coercion ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_copy_coerces_missing_width_height_to_zero() -> None:
    # L322-323: `width = int(url_info.get("width", 0) or 0)` — defensive against
    # rows where width/height keys are missing or null.
    disk = _InMemoryDisk()
    disk.files["1/responsive-images/a.jpg"] = b"bytes"
    src_responsive: dict[str, Any] = {
        "original": {
            "urls": [
                {"path": "1/responsive-images/a.jpg"},  # no width/height
            ],
            "base64svg": "",
        }
    }
    result = await copy_responsive_images(src_responsive, new_media_id=2, disk=disk)
    assert len(result["original"]["urls"]) == 1
    new_url = result["original"]["urls"][0]
    assert new_url["width"] == 0
    assert new_url["height"] == 0
