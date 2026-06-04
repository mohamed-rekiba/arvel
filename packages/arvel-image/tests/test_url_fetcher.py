"""url_fetcher — happy paths and size/HTTP failure modes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Self

import httpx
import pytest
from arvel_image.media.exceptions import MediaError
from arvel_image.media.url_fetcher import fetch_url

_HTTP_ERROR_THRESHOLD = 400


class _FakeResponse:
    def __init__(self, headers: dict[str, str], status_code: int, chunks: list[bytes]) -> None:
        self.headers = headers
        self.status_code = status_code
        self._chunks = chunks

    def raise_for_status(self) -> None:
        if self.status_code >= _HTTP_ERROR_THRESHOLD:
            raise httpx.HTTPStatusError(
                "boom",
                request=httpx.Request("GET", "http://example.com/"),
                response=httpx.Response(self.status_code),
            )

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


class _FakeStream:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    async def __aenter__(self) -> _FakeResponse:
        return self._response

    async def __aexit__(self, *_exc: object) -> None:
        return None


def _make_fake_client(state: dict[str, Any]) -> type:
    """Returns a class whose stream() reads from ``state`` each call."""

    class _FakeClient:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        def stream(self, _method: str, _url: str) -> _FakeStream:
            return _FakeStream(
                _FakeResponse(
                    headers=state["headers"],
                    status_code=state["status_code"],
                    chunks=state["chunks"],
                )
            )

    return _FakeClient


def _noop_ssrf_guard(_host: str) -> None:
    """Drop-in replacement for `reject_private_ip` used by `bypass_ssrf_guard`."""


@pytest.fixture
def bypass_ssrf_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip the DNS-resolution + IP check so tests can use any host string."""
    monkeypatch.setattr("arvel_image.media.url_fetcher.reject_private_ip", _noop_ssrf_guard)


@pytest.fixture
def mock_httpx_stream(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch httpx.AsyncClient so .stream() yields configurable bytes + headers."""
    state: dict[str, Any] = {
        "chunks": [b"hello world"],
        "headers": {"content-length": "11"},
        "status_code": 200,
    }
    monkeypatch.setattr(httpx, "AsyncClient", _make_fake_client(state))
    return state


# ── happy path ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_url_returns_bytes_and_derived_filename(
    bypass_ssrf_guard: None, mock_httpx_stream: dict[str, Any]
) -> None:
    mock_httpx_stream["chunks"] = [b"abc", b"def"]
    mock_httpx_stream["headers"] = {}

    content, name = await fetch_url("https://example.com/path/photo.jpg", max_bytes=1024)
    assert content == b"abcdef"
    assert name == "photo.jpg"


@pytest.mark.asyncio
async def test_fetch_url_falls_back_to_download_when_no_filename(
    bypass_ssrf_guard: None, mock_httpx_stream: dict[str, Any]
) -> None:
    """A URL ending in `/` yields the default `download` filename."""
    mock_httpx_stream["chunks"] = [b"x"]
    mock_httpx_stream["headers"] = {}

    _, name = await fetch_url("https://example.com/", max_bytes=1024)
    assert name == "download"


@pytest.mark.asyncio
async def test_fetch_url_falls_back_to_download_for_bare_host(
    bypass_ssrf_guard: None, mock_httpx_stream: dict[str, Any]
) -> None:
    mock_httpx_stream["chunks"] = [b"x"]
    mock_httpx_stream["headers"] = {}

    _, name = await fetch_url("https://example.com", max_bytes=1024)
    assert name == "download"


# ── size cap: streaming guard ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_url_streaming_aborts_when_chunks_exceed_cap(
    bypass_ssrf_guard: None, mock_httpx_stream: dict[str, Any]
) -> None:
    """Slow-loris guard — chunks accumulating past max_bytes raise."""
    mock_httpx_stream["chunks"] = [b"a" * 100, b"b" * 100]
    mock_httpx_stream["headers"] = {}

    with pytest.raises(MediaError, match="max_bytes=150"):
        await fetch_url("https://example.com/big", max_bytes=150)


# ── size cap: content-length pre-check ──────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_url_rejects_oversize_content_length_header(
    bypass_ssrf_guard: None, mock_httpx_stream: dict[str, Any]
) -> None:
    mock_httpx_stream["chunks"] = [b"x"]
    mock_httpx_stream["headers"] = {"content-length": "999999"}

    with pytest.raises(MediaError, match="max_bytes=1024"):
        await fetch_url("https://example.com/big", max_bytes=1024)


@pytest.mark.asyncio
async def test_fetch_url_ignores_non_numeric_content_length(
    bypass_ssrf_guard: None, mock_httpx_stream: dict[str, Any]
) -> None:
    """A garbage Content-Length header doesn't block the download — chunks decide."""
    mock_httpx_stream["chunks"] = [b"ok"]
    mock_httpx_stream["headers"] = {"content-length": "not-a-number"}

    content, _ = await fetch_url("https://example.com/file.txt", max_bytes=1024)
    assert content == b"ok"


# ── HTTP error mapping ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_url_propagates_http_status_errors(
    bypass_ssrf_guard: None, mock_httpx_stream: dict[str, Any]
) -> None:
    mock_httpx_stream["status_code"] = 404

    with pytest.raises(httpx.HTTPStatusError):
        await fetch_url("https://example.com/missing", max_bytes=1024)


# ── scheme rejection (real, no mock) ───────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_url_rejects_unsupported_scheme() -> None:
    with pytest.raises(MediaError, match="not permitted"):
        await fetch_url("ftp://example.com/", max_bytes=1024)
