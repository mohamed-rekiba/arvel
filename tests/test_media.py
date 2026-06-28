"""Phase 10 — Image (Pillow) + Video (av) managers."""

from __future__ import annotations

from arvel.media import Image, ImageManager, Video, VideoManager


def test_image_make_and_dimensions() -> None:
    image = Image.make(20, 10, "red")
    assert image.width == 20
    assert image.height == 10


def test_image_resize_crop_convert_chain() -> None:
    image = Image.make(20, 20)
    resized = image.resize(10, 8)
    assert (resized.width, resized.height) == (10, 8)
    cropped = resized.crop(0, 0, 5, 5)
    assert (cropped.width, cropped.height) == (5, 5)
    assert cropped.convert("L").raw.mode == "L"


def test_image_encode_roundtrip() -> None:
    data = Image.make(8, 8, "blue").encode("PNG")
    assert data[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic
    reopened = Image.open(data)
    assert reopened.width == 8


def test_image_manager_open_make() -> None:
    manager = ImageManager()
    png = manager.make(4, 4).encode("PNG")
    assert manager.open(png).width == 4


def test_video_manager_exists() -> None:
    # Opening a real container is exercised by the G4 fidelity check; here we just
    # assert the manager surface is present (av is heavy to synthesize twice).
    assert hasattr(VideoManager(), "open")
    assert hasattr(Video, "open")
