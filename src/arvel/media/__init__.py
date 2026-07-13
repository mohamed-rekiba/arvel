"""arvel.media — Image on **Pillow** + Video on **av** (PyAV) (mandated engines).

``Image.open(...)`` / ``Image.make(w, h)`` wrap a real ``PIL.Image.Image`` (resize/crop/
convert/encode); ``Video.open(path)`` wraps a real ``av`` container (probe duration/
streams). Heavy libs are imported lazily so ``import arvel`` stays light. The ``HasMedia``
mixin (media collections + generated conversions, Spatie-medialibrary style, stored on a
Storage disk) lives in :mod:`arvel.media.library`. Grounded in knowledge/port/16-managers.md.
"""

from __future__ import annotations

import io
from typing import Any

from arvel.media.library import HasMedia, Media, MediaAdder, MediaConversion


def _pil() -> Any:
    """Pillow's typing is incomplete for our use — funnel it through Any here."""
    from PIL import Image as PILImage

    return PILImage


def _av() -> Any:
    """av (PyAV) ships no type stubs — funnel it through Any at this single boundary."""
    import av

    return av


class Image:
    """A thin wrapper over a ``PIL.Image.Image`` (fluent, immutable transforms)."""

    def __init__(self, image: Any) -> None:
        self._image = image

    @property
    def raw(self) -> Any:
        return self._image

    @property
    def width(self) -> int:
        return int(self._image.width)

    @property
    def height(self) -> int:
        return int(self._image.height)

    @classmethod
    def open(cls, source: bytes | str) -> Image:
        handle = io.BytesIO(source) if isinstance(source, bytes) else source
        return cls(_pil().open(handle))

    @classmethod
    def make(cls, width: int, height: int, color: str = "white") -> Image:
        return cls(_pil().new("RGB", (width, height), color))

    def resize(self, width: int, height: int) -> Image:
        return Image(self._image.resize((width, height)))

    def crop(self, left: int, top: int, right: int, bottom: int) -> Image:
        return Image(self._image.crop((left, top, right, bottom)))

    def convert(self, mode: str) -> Image:
        return Image(self._image.convert(mode))

    def encode(self, image_format: str = "PNG") -> bytes:
        buffer = io.BytesIO()
        self._image.save(buffer, format=image_format)
        return buffer.getvalue()


class ImageManager:
    """DI-friendly entry to image operations (``Image.open``/``make`` under the hood)."""

    def open(self, source: bytes | str) -> Image:
        return Image.open(source)

    def make(self, width: int, height: int, color: str = "white") -> Image:
        return Image.make(width, height, color)


class Video:
    """A thin wrapper over a real ``av`` container (probe metadata; transcode later)."""

    def __init__(self, container: Any) -> None:
        self._container = container

    @property
    def raw(self) -> Any:
        return self._container

    @classmethod
    def open(cls, path: str) -> Video:
        return cls(_av().open(path))

    def duration(self) -> Any:
        return self._container.duration

    def streams_info(self) -> list[dict[str, Any]]:
        return [{"type": stream.type} for stream in self._container.streams]

    def frame_at(self, seconds: float = 0.0) -> Image:
        """Decode a single frame at ~``seconds`` into the video as an :class:`Image` — a poster or
        thumbnail. Seeks to the nearest preceding keyframe, so the frame is at or just before
        ``seconds``. CPU-bound (decode): offload it off the event loop on a request path."""
        stream = self._container.streams.video[0]
        if seconds > 0:
            self._container.seek(int(seconds / stream.time_base), backward=True, stream=stream)
        for frame in self._container.decode(stream):
            return Image(frame.to_image())
        raise ValueError("no decodable video frame")

    def transcode(self, output_path: str, *, codec: str = "mpeg4", rate: int | None = None) -> None:
        """Re-encode the video stream to ``output_path`` (container chosen by its extension) using
        ``codec``. CPU-bound (a full decode/encode pass): offload it off the event loop."""
        source = self._container.streams.video[0]
        output = _av().open(output_path, mode="w")
        try:
            out_stream = output.add_stream(codec, rate=rate or source.average_rate or 25)
            out_stream.width = source.width
            out_stream.height = source.height
            out_stream.pix_fmt = "yuv420p"
            for frame in self._container.decode(source):
                output.mux(out_stream.encode(frame))
            output.mux(out_stream.encode())  # flush the encoder
        finally:
            output.close()

    def close(self) -> None:
        self._container.close()


class VideoManager:
    """DI-friendly entry to video operations."""

    def open(self, path: str) -> Video:
        return Video.open(path)


__all__ = [
    "HasMedia",
    "Image",
    "ImageManager",
    "Media",
    "MediaAdder",
    "MediaConversion",
    "Video",
    "VideoManager",
]
