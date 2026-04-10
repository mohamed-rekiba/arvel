"""Tests for ImageProcessor — Pillow-based image resize and compression.

Covers: fit modes, output format, quality, RGBA→RGB conversion, error handling,
is_processable helper, MediaManager conversion pipeline, process=False flag,
and MediaFake conversion simulation.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from arvel.media.config import MediaSettings
from arvel.media.exceptions import MediaProcessingError
from arvel.media.fakes import MediaFake
from arvel.media.image_processor import ImageProcessor, is_processable
from arvel.media.types import Conversion, MediaCollection


def _make_jpeg(width: int = 200, height: int = 200, *, color: str = "red") -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _make_png(width: int = 200, height: int = 200, *, rgba: bool = False) -> bytes:
    mode = "RGBA" if rgba else "RGB"
    img = Image.new(mode, (width, height), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_webp(width: int = 200, height: int = 200) -> bytes:
    img = Image.new("RGB", (width, height), color="green")
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=95)
    return buf.getvalue()


def _image_size(data: bytes) -> tuple[int, int]:
    img = Image.open(io.BytesIO(data))
    return img.size


class TestIsProcessable:
    def test_jpeg_is_processable(self) -> None:
        assert is_processable("image/jpeg") is True

    def test_png_is_processable(self) -> None:
        assert is_processable("image/png") is True

    def test_webp_is_processable(self) -> None:
        assert is_processable("image/webp") is True

    def test_gif_is_processable(self) -> None:
        assert is_processable("image/gif") is True

    def test_pdf_not_processable(self) -> None:
        assert is_processable("application/pdf") is False

    def test_plaintext_not_processable(self) -> None:
        assert is_processable("text/plain") is False

    def test_octet_stream_not_processable(self) -> None:
        assert is_processable("application/octet-stream") is False


class TestImageProcessorFitModes:
    """Cover → crops to exact size, contain → fits within, fill → stretches."""

    def test_cover_produces_exact_dimensions(self) -> None:
        proc = ImageProcessor(quality=80)
        src = _make_jpeg(400, 300)
        conv = Conversion(name="thumb", width=100, height=100, fit="cover")

        result, mime = proc.process(src, conv, source_mime="image/jpeg")

        w, h = _image_size(result)
        assert (w, h) == (100, 100)
        assert mime == "image/jpeg"

    def test_contain_fits_within_bounds(self) -> None:
        proc = ImageProcessor(quality=80)
        src = _make_jpeg(400, 200)
        conv = Conversion(name="preview", width=100, height=100, fit="contain")

        result, _mime = proc.process(src, conv, source_mime="image/jpeg")

        w, h = _image_size(result)
        assert w <= 100
        assert h <= 100
        assert w == 100 or h == 100

    def test_fill_stretches_to_exact_dimensions(self) -> None:
        proc = ImageProcessor(quality=80)
        src = _make_jpeg(400, 200)
        conv = Conversion(name="banner", width=150, height=50, fit="fill")

        result, _ = proc.process(src, conv, source_mime="image/jpeg")

        w, h = _image_size(result)
        assert (w, h) == (150, 50)

    def test_inside_fits_within_bounds(self) -> None:
        proc = ImageProcessor(quality=80)
        src = _make_jpeg(400, 200)
        conv = Conversion(name="inside", width=100, height=100, fit="inside")

        result, _ = proc.process(src, conv, source_mime="image/jpeg")

        w, h = _image_size(result)
        assert w <= 100 and h <= 100

    def test_unknown_fit_raises(self) -> None:
        proc = ImageProcessor(quality=80)
        src = _make_jpeg(100, 100)
        conv = Conversion(name="bad", width=50, height=50, fit="stretch_magic")

        with pytest.raises(MediaProcessingError, match="Unknown fit mode"):
            proc.process(src, conv, source_mime="image/jpeg")


class TestImageProcessorFormats:
    def test_source_format_preserves_jpeg(self) -> None:
        proc = ImageProcessor(output_format="source")
        src = _make_jpeg()
        conv = Conversion(name="t", width=50, height=50)

        _, mime = proc.process(src, conv, source_mime="image/jpeg")
        assert mime == "image/jpeg"

    def test_source_format_preserves_png(self) -> None:
        proc = ImageProcessor(output_format="source")
        src = _make_png()
        conv = Conversion(name="t", width=50, height=50)

        _, mime = proc.process(src, conv, source_mime="image/png")
        assert mime == "image/png"

    def test_convert_to_webp(self) -> None:
        proc = ImageProcessor(output_format="webp")
        src = _make_jpeg()
        conv = Conversion(name="t", width=50, height=50)

        result, mime = proc.process(src, conv, source_mime="image/jpeg")

        assert mime == "image/webp"
        img = Image.open(io.BytesIO(result))
        assert img.format == "WEBP"

    def test_convert_png_to_jpeg(self) -> None:
        proc = ImageProcessor(output_format="jpeg")
        src = _make_png()
        conv = Conversion(name="t", width=50, height=50)

        _result, mime = proc.process(src, conv, source_mime="image/png")

        assert mime == "image/jpeg"

    def test_rgba_png_to_jpeg_converts_to_rgb(self) -> None:
        proc = ImageProcessor(output_format="jpeg")
        src = _make_png(rgba=True)
        conv = Conversion(name="t", width=50, height=50)

        result, mime = proc.process(src, conv, source_mime="image/png")

        assert mime == "image/jpeg"
        img = Image.open(io.BytesIO(result))
        assert img.mode == "RGB"


class TestImageProcessorQuality:
    def test_lower_quality_produces_smaller_file(self) -> None:
        src = _make_jpeg(400, 400)
        conv = Conversion(name="t", width=200, height=200)

        high = ImageProcessor(quality=95)
        low = ImageProcessor(quality=30)

        result_high, _ = high.process(src, conv, source_mime="image/jpeg")
        result_low, _ = low.process(src, conv, source_mime="image/jpeg")

        assert len(result_low) < len(result_high)

    def test_invalid_quality_raises(self) -> None:
        with pytest.raises(ValueError, match="quality must be 1-100"):
            ImageProcessor(quality=0)

        with pytest.raises(ValueError, match="quality must be 1-100"):
            ImageProcessor(quality=101)


class TestImageProcessorErrors:
    def test_unsupported_mime_raises(self) -> None:
        proc = ImageProcessor()
        conv = Conversion(name="t", width=50, height=50)

        with pytest.raises(MediaProcessingError, match="Unsupported image MIME"):
            proc.process(b"not an image", conv, source_mime="application/pdf")

    def test_corrupt_image_raises(self) -> None:
        proc = ImageProcessor()
        conv = Conversion(name="t", width=50, height=50)

        with pytest.raises(MediaProcessingError, match="Failed to open image"):
            proc.process(b"garbage bytes", conv, source_mime="image/jpeg")


class TestMediaManagerConversions:
    """Integration: MediaManager stores original + generates conversion derivatives."""

    async def test_add_with_conversions_populates_media_conversions(self) -> None:
        storage = _FakeStorage()
        settings = MediaSettings()
        from arvel.media.manager import MediaManager

        manager = MediaManager(storage=storage, settings=settings)  # ty: ignore[invalid-argument-type]
        manager.register_collection(
            dict,
            MediaCollection(
                name="avatars",
                conversions=[
                    Conversion(name="thumb", width=100, height=100),
                    Conversion(name="small", width=200, height=200),
                ],
            ),
        )

        model = {"type": "User", "id": 1}
        media = await manager.add(
            model,
            _make_jpeg(400, 400),
            "photo.jpg",
            collection="avatars",
            content_type="image/jpeg",
        )

        assert "thumb" in media.conversions
        assert "small" in media.conversions
        assert "conversions/thumb/" in media.conversions["thumb"]
        assert "conversions/small/" in media.conversions["small"]

    async def test_add_stores_original_and_conversions(self) -> None:
        storage = _FakeStorage()
        settings = MediaSettings()
        from arvel.media.manager import MediaManager

        manager = MediaManager(storage=storage, settings=settings)  # ty: ignore[invalid-argument-type]
        manager.register_collection(
            dict,
            MediaCollection(
                name="photos",
                conversions=[Conversion(name="thumb", width=50, height=50)],
            ),
        )

        model = {"type": "User", "id": 1}
        await manager.add(
            model,
            _make_jpeg(200, 200),
            "photo.jpg",
            collection="photos",
            content_type="image/jpeg",
        )

        # original + 1 conversion = 2 storage.put calls
        assert len(storage.stored) == 2

    async def test_add_with_process_false_skips_conversions(self) -> None:
        storage = _FakeStorage()
        settings = MediaSettings()
        from arvel.media.manager import MediaManager

        manager = MediaManager(storage=storage, settings=settings)  # ty: ignore[invalid-argument-type]
        manager.register_collection(
            dict,
            MediaCollection(
                name="avatars",
                conversions=[Conversion(name="thumb", width=100, height=100)],
            ),
        )

        model = {"type": "User", "id": 1}
        media = await manager.add(
            model,
            _make_jpeg(400, 400),
            "photo.jpg",
            collection="avatars",
            content_type="image/jpeg",
            process=False,
        )

        assert media.conversions == {}
        assert len(storage.stored) == 1  # only original

    async def test_add_non_image_skips_conversions(self) -> None:
        storage = _FakeStorage()
        settings = MediaSettings()
        from arvel.media.manager import MediaManager

        manager = MediaManager(storage=storage, settings=settings)  # ty: ignore[invalid-argument-type]
        manager.register_collection(
            dict,
            MediaCollection(
                name="docs",
                conversions=[Conversion(name="thumb", width=100, height=100)],
            ),
        )

        model = {"type": "User", "id": 1}
        media = await manager.add(
            model,
            b"not an image",
            "readme.txt",
            collection="docs",
            content_type="text/plain",
        )

        assert media.conversions == {}
        assert len(storage.stored) == 1

    async def test_add_without_collection_skips_conversions(self) -> None:
        storage = _FakeStorage()
        settings = MediaSettings()
        from arvel.media.manager import MediaManager

        manager = MediaManager(storage=storage, settings=settings)  # ty: ignore[invalid-argument-type]

        model = {"type": "User", "id": 1}
        media = await manager.add(
            model,
            _make_jpeg(200, 200),
            "photo.jpg",
            content_type="image/jpeg",
        )

        assert media.conversions == {}

    async def test_conversion_dimensions_are_correct(self) -> None:
        storage = _FakeStorage()
        settings = MediaSettings()
        from arvel.media.manager import MediaManager

        manager = MediaManager(storage=storage, settings=settings)  # ty: ignore[invalid-argument-type]
        manager.register_collection(
            dict,
            MediaCollection(
                name="avatars",
                conversions=[Conversion(name="thumb", width=80, height=80, fit="cover")],
            ),
        )

        model = {"type": "User", "id": 1}
        await manager.add(
            model,
            _make_jpeg(400, 300),
            "photo.jpg",
            collection="avatars",
            content_type="image/jpeg",
        )

        conv_bytes = storage.stored[1][1]  # second put call is the conversion
        w, h = _image_size(conv_bytes)
        assert (w, h) == (80, 80)


class TestMediaFakeConversions:
    """MediaFake populates conversions dict when collection has conversions."""

    async def test_fake_populates_conversions(self) -> None:
        fake = MediaFake()
        fake.register_collection(
            dict,
            MediaCollection(
                name="avatars",
                conversions=[Conversion(name="thumb", width=100, height=100)],
            ),
        )

        model = {"type": "User", "id": 1}
        media = await fake.add(
            model, b"img", "photo.jpg", collection="avatars", content_type="image/jpeg"
        )

        assert "thumb" in media.conversions

    async def test_fake_skips_conversions_when_process_false(self) -> None:
        fake = MediaFake()
        fake.register_collection(
            dict,
            MediaCollection(
                name="avatars",
                conversions=[Conversion(name="thumb", width=100, height=100)],
            ),
        )

        model = {"type": "User", "id": 1}
        media = await fake.add(
            model,
            b"img",
            "photo.jpg",
            collection="avatars",
            content_type="image/jpeg",
            process=False,
        )

        assert media.conversions == {}

    async def test_fake_no_conversions_without_collection(self) -> None:
        fake = MediaFake()
        model = {"type": "User", "id": 1}
        media = await fake.add(model, b"img", "photo.jpg")
        assert media.conversions == {}


class TestMediaSettingsConversion:
    def test_default_quality(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MEDIA_CONVERSION_QUALITY", raising=False)
        monkeypatch.delenv("MEDIA_CONVERSION_FORMAT", raising=False)
        settings = MediaSettings()
        assert settings.conversion_quality == 85

    def test_default_format(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MEDIA_CONVERSION_FORMAT", raising=False)
        settings = MediaSettings()
        assert settings.conversion_format == "source"

    def test_quality_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MEDIA_CONVERSION_QUALITY", "60")
        settings = MediaSettings()
        assert settings.conversion_quality == 60

    def test_format_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MEDIA_CONVERSION_FORMAT", "webp")
        settings = MediaSettings()
        assert settings.conversion_format == "webp"


# ── Helpers ──────────────────────────────────────────────────


class _FakeStorage:
    """Minimal StorageContract double for MediaManager tests."""

    def __init__(self) -> None:
        self.stored: list[tuple[str, bytes, str | None]] = []

    async def put(self, path: str, data: bytes, *, content_type: str | None = None) -> None:
        self.stored.append((path, data, content_type))

    async def url(self, path: str) -> str:
        return f"/storage/{path}"

    async def delete(self, path: str) -> None:
        self.stored = [(p, d, ct) for p, d, ct in self.stored if p != path]
