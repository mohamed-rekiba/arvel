"""Method spoof middleware branch coverage."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast

import pytest
from arvel.http.middleware import method_spoof
from starlette.types import Message, Receive, Scope

_Header = Callable[[Scope, bytes], str | None]
_ExtractMethod = Callable[[bytes, str], str | None]
_BufferBody = Callable[[Receive], Awaitable[tuple[bytes, Receive]]]


def _header_func() -> _Header:
    return cast("_Header", object.__getattribute__(method_spoof, "_header"))


def _extract_method_func() -> _ExtractMethod:
    return cast("_ExtractMethod", object.__getattribute__(method_spoof, "_extract_method"))


def _extract_method_multipart_func() -> _ExtractMethod:
    return cast(
        "_ExtractMethod",
        object.__getattribute__(method_spoof, "_extract_method_multipart"),
    )


def _buffer_body_func() -> _BufferBody:
    return cast("_BufferBody", object.__getattribute__(method_spoof, "_buffer_body"))


def test_header_returns_none_when_absent() -> None:
    assert _header_func()({"type": "http", "headers": []}, b"content-type") is None


def test_header_decodes_present_value() -> None:
    scope: Scope = {"type": "http", "headers": [(b"content-type", b"multipart/form-data")]}
    assert _header_func()(scope, b"content-type") == "multipart/form-data"


def test_extract_method_urlencoded_strips_and_uppercases() -> None:
    assert (
        _extract_method_func()(b"name=x&_method=+put+", "application/x-www-form-urlencoded")
        == "PUT"
    )


def test_extract_method_urlencoded_invalid_utf8_returns_none() -> None:
    assert _extract_method_func()(b"\xff\xfe", "application/x-www-form-urlencoded") is None


def test_extract_method_urlencoded_missing_field_returns_none() -> None:
    assert _extract_method_func()(b"name=x", "application/x-www-form-urlencoded") is None


def test_multipart_boundary_missing_returns_none() -> None:
    assert _extract_method_multipart_func()(b"", "multipart/form-data") is None


def test_multipart_extracts_method_field() -> None:
    body = b'--abc\r\nContent-Disposition: form-data; name="_method"\r\n\r\npatch\r\n--abc--\r\n'
    assert _extract_method_multipart_func()(body, "multipart/form-data; boundary=abc") == "PATCH"


def test_multipart_marker_missing_returns_none() -> None:
    body = b'--abc\r\nContent-Disposition: form-data; name="name"\r\n\r\nvalue\r\n--abc--\r\n'
    assert _extract_method_multipart_func()(body, "multipart/form-data; boundary=abc") is None


def test_multipart_missing_blank_line_returns_none() -> None:
    body = b'--abc\r\nContent-Disposition: form-data; name="_method"\r\npatch\r\n--abc--\r\n'
    assert _extract_method_multipart_func()(body, "multipart/form-data; boundary=abc") is None


def test_multipart_missing_end_boundary_returns_none() -> None:
    body = b'--abc\r\nContent-Disposition: form-data; name="_method"\r\n\r\npatch\r\n'
    assert _extract_method_multipart_func()(body, "multipart/form-data; boundary=abc") is None


@pytest.mark.asyncio
async def test_buffer_body_replays_request_then_disconnects() -> None:
    raw_messages: list[Message] = [
        {"type": "http.request", "body": b"hello", "more_body": False},
    ]
    messages = iter(raw_messages)

    async def receive() -> Message:
        return next(messages)

    body, replay = await _buffer_body_func()(receive)

    assert body == b"hello"
    assert await replay() == {"type": "http.request", "body": b"hello", "more_body": False}
    assert await replay() == {"type": "http.disconnect"}
