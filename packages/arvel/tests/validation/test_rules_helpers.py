"""Image-dimension and exists rules, exercised through their public handlers.

Driving the public ``rule_dimensions`` / ``rule_exists`` entry points keeps the
image parser, identifier guard, and dimension math covered without reaching
into private helpers.
"""

from __future__ import annotations

import struct
import zlib

import pytest
from arvel.validation.rules import rule_dimensions, rule_exists


def _png(width: int, height: int) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IEND", b"")


async def test_dimensions_skips_none_value() -> None:
    assert await rule_dimensions("avatar", None, [], {}, None) is None


async def test_dimensions_rejects_non_image_bytes() -> None:
    assert await rule_dimensions("avatar", b"not-an-image", [], {}, None) == (
        "The avatar must be an image."
    )


@pytest.mark.parametrize(
    "data",
    [
        b"\xff\xd8\x00\x00",  # byte after SOI isn't a marker
        b"\xff\xd8\xff\xd8",  # SOI/EOI marker hits the skip branch, buffer ends
        b"\xff\xd8\xff\xc4",  # truncated right after a marker
        b"\xff\xd8\xff\xc4\x00\x01",  # segment length below the minimum
        b"\xff\xd8\xff\xc0\x00\x10",  # SOF marker but not enough bytes for dimensions
        b"\xff\xd8\xff\xc4\x00\x04\xaa\xbb",  # valid non-SOF segment, then buffer ends
    ],
)
async def test_dimensions_rejects_malformed_jpeg(data: bytes) -> None:
    assert await rule_dimensions("avatar", data, [], {}, None) == "The avatar must be an image."


async def test_dimensions_malformed_constraint_param() -> None:
    msg = await rule_dimensions("avatar", _png(50, 50), ["min_width"], {}, None)
    assert msg is not None
    assert "Invalid dimensions parameter" in msg


async def test_dimensions_reports_violation() -> None:
    msg = await rule_dimensions("avatar", _png(50, 50), ["min_width=100"], {}, None)
    assert msg == "The avatar must be at least 100 pixels wide."


async def test_dimensions_passes_within_constraints() -> None:
    assert await rule_dimensions("avatar", _png(50, 50), ["min_width=10"], {}, None) is None


async def test_dimensions_reads_async_file_like() -> None:
    class _AsyncFile:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        async def read(self) -> bytes:
            return self._payload

    result = await rule_dimensions("avatar", _AsyncFile(_png(20, 20)), ["min_width=10"], {}, None)
    assert result is None


async def test_dimensions_non_bytes_read_is_not_an_image() -> None:
    class _StrFile:
        def read(self) -> str:
            return "not bytes"

    result = await rule_dimensions("avatar", _StrFile(), [], {}, None)
    assert result == "The avatar must be an image."


async def test_exists_rejects_unsafe_table_identifier() -> None:
    # The identifier guard runs before any session access, so a bad table name
    # raises straight out of the public handler.
    with pytest.raises(ValueError, match="Invalid SQL table"):
        await rule_exists("country", "x", ["bad name", "id"], {}, None)
