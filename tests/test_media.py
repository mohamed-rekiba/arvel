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
    # real container open is covered by the G4 fidelity check; av is heavy to synthesize twice
    assert hasattr(VideoManager(), "open")
    assert hasattr(Video, "open")


def _make_video(path: str, *, frames: int = 12, width: int = 64, height: int = 48) -> None:
    """Write a tiny real mp4 (av only, no numpy) for the processing tests below."""
    import av

    out = av.open(path, mode="w")
    stream = out.add_stream("mpeg4", rate=6)
    stream.width, stream.height, stream.pix_fmt = width, height, "yuv420p"
    for _ in range(frames):
        for packet in stream.encode(av.VideoFrame(width, height, "yuv420p")):
            out.mux(packet)
    for packet in stream.encode():  # flush
        out.mux(packet)
    out.close()


def test_frame_at_extracts_an_image(tmp_path: object) -> None:
    src = f"{tmp_path}/clip.mp4"
    _make_video(src)
    video = Video.open(src)
    try:
        frame = video.frame_at(0.5)
        assert isinstance(frame, Image)
        assert (frame.width, frame.height) == (64, 48)
    finally:
        video.close()


def test_transcode_writes_a_decodable_video(tmp_path: object) -> None:
    src, dst = f"{tmp_path}/in.mp4", f"{tmp_path}/out.mp4"
    _make_video(src)
    video = Video.open(src)
    try:
        video.transcode(dst, codec="mpeg4")
    finally:
        video.close()

    out = Video.open(dst)
    try:
        assert any(s["type"] == "video" for s in out.streams_info())
        assert isinstance(out.frame_at(0), Image)  # the re-encoded file is decodable
    finally:
        out.close()
