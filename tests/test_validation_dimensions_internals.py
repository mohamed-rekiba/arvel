"""arvel.validation internals — the sync upload byte-reader and the dimensions constraint checks
that the public ``dimensions`` rule funnels through, exercised on the file-like read paths and
each failing constraint branch."""

from __future__ import annotations

import io

from PIL import Image

from arvel.validation import (
    _check_dimensions,  # pyright: ignore[reportPrivateUsage]
    _parse_ratio,  # pyright: ignore[reportPrivateUsage]
    _upload_bytes,  # pyright: ignore[reportPrivateUsage]
)


def _png(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height)).save(buf, format="PNG")
    return buf.getvalue()


class _UploadFile:
    """A litestar-style upload: bytes live behind a sync ``.file`` file object."""

    def __init__(self, data: bytes) -> None:
        self.file = io.BytesIO(data)


class _Readable:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


def test_upload_bytes_reads_each_supported_shape() -> None:
    data = _png(10, 10)
    assert _upload_bytes(data) == data  # raw bytes
    assert _upload_bytes(bytearray(data)) == data  # bytearray
    assert _upload_bytes(_UploadFile(data)) == data  # .file (seek + read)
    assert _upload_bytes(_Readable(data)) == data  # sync .read()
    assert _upload_bytes(object()) is None  # unsupported
    assert _upload_bytes(_Readable("not-bytes")) is None  # reader returns non-bytes


def test_parse_ratio_plain_number() -> None:
    assert _parse_ratio("1.5") == 1.5
    assert _parse_ratio("3/2") == 1.5


def test_check_dimensions_each_failing_constraint() -> None:
    img = _png(100, 50)
    assert _check_dimensions(img, "width=100,height=50") is True
    assert _check_dimensions(img, "height=49") is False
    assert _check_dimensions(img, "min_height=100") is False
    assert _check_dimensions(img, "max_width=50") is False
    assert _check_dimensions(img, "max_height=10") is False
    assert _check_dimensions(b"garbage", "min_width=1") is False  # unopenable
    assert _check_dimensions(object(), "min_width=1") is False  # not readable
