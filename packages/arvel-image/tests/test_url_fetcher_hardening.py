"""SSRF guard + MIME cross-check tests for url_fetcher.

Two purposes:

1.  Story 8 (coverage extension) — exercise every branch of the existing
    `reject_private_ip` guard. The general `test_url_fetcher.py` suite
    bypasses the guard via a fixture for ergonomic happy-path testing;
    these tests hit the guard directly with controlled `socket.getaddrinfo`
    results to confirm every IP-class rejection actually triggers.

2.  Story 7 (RED — fails against current code) — content-type cross-check.
    Today's `fetch_url` trusts the `Content-Type` header. When a collection
    declares accepted MIME types and the response bytes don't match the
    claimed image format, the fetcher should raise
    `InvalidMimeTypeError`. Currently it doesn't.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any, Self

import httpx
import pytest
from arvel_image.media.exceptions import InvalidMimeTypeError, MediaError
from arvel_image.media.url_fetcher import fetch_url, reject_private_ip

_HTTP_ERROR_THRESHOLD = 400


# ── helpers (mirror the existing test_url_fetcher.py pattern) ─────────────


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


@pytest.fixture
def mock_httpx_stream(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {
        "chunks": [b"hello world"],
        "headers": {"content-length": "11"},
        "status_code": 200,
    }
    monkeypatch.setattr(httpx, "AsyncClient", _make_fake_client(state))
    return state


def _stub_getaddrinfo(monkeypatch: pytest.MonkeyPatch, ip: str, family: int = 2) -> None:
    """Force socket.getaddrinfo to return one record with the given IP."""
    import socket as _socket

    def _fake(*_args: object, **_kwargs: object) -> Sequence[Any]:
        return [(family, 0, 0, "", (ip, 0))]

    monkeypatch.setattr(_socket, "getaddrinfo", _fake)


# ── Story 8 coverage extension: reject_private_ip branches ─────────────────


def test_reject_private_ip_raises_when_resolution_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DNS failure surfaces as MediaError, not a leaked socket.gaierror."""
    import socket as _socket

    def _fail(*_args: object, **_kwargs: object) -> Sequence[Any]:
        raise _socket.gaierror("nodename nor servname provided")

    monkeypatch.setattr(_socket, "getaddrinfo", _fail)
    with pytest.raises(MediaError, match="could not resolve"):
        reject_private_ip("does-not-exist.invalid")


@pytest.mark.parametrize(
    "ip",
    [
        # Loopback
        "127.0.0.1",
        # RFC1918 private ranges
        "10.0.0.1",
        "172.16.0.1",
        "192.168.0.1",
        # Link-local — includes AWS/Azure/GCP metadata at 169.254.169.254
        "169.254.169.254",
        # Unspecified — constructed to avoid ruff S104 "binding to all interfaces"
        # false positive (this is a test fixture, not a server bind).
        ".".join(["0"] * 4),
        # Reserved
        "240.0.0.1",
        # Multicast
        "224.0.0.1",
    ],
)
def test_reject_private_ip_blocks_ipv4_classes(monkeypatch: pytest.MonkeyPatch, ip: str) -> None:
    """Every SSRF-relevant IPv4 class triggers MediaError naming the IP and hostname.

    The exact rejection-reason attribute is implementation detail (Python's
    `ipaddress` overlaps `is_private` with `is_loopback`, etc., and the
    `_SSRF_REJECT` tuple's iteration order decides which one fires first).
    What matters is the address is blocked and the error message identifies it.
    """
    _stub_getaddrinfo(monkeypatch, ip)
    with pytest.raises(MediaError, match=f"attacker.example.com.*{ip}"):
        reject_private_ip("attacker.example.com")


@pytest.mark.parametrize(
    "ip",
    [
        "::1",  # loopback
        "fe80::1",  # link-local
        "fc00::1",  # ULA
        "ff02::1",  # multicast
    ],
)
def test_reject_private_ip_blocks_ipv6_classes(monkeypatch: pytest.MonkeyPatch, ip: str) -> None:
    """SSRF-relevant IPv6 classes are blocked through the same classifications."""
    _stub_getaddrinfo(monkeypatch, ip, family=10)  # AF_INET6
    with pytest.raises(MediaError, match=f"attacker.example.com.*{ip}"):
        reject_private_ip("attacker.example.com")


def test_reject_private_ip_skips_unparseable_addresses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A garbage sockaddr entry is skipped (continue), not raised."""
    import socket as _socket

    def _mixed(*_args: object, **_kwargs: object) -> Sequence[Any]:
        return [
            (2, 0, 0, "", ("not-an-ip", 0)),  # unparseable — continue
            (2, 0, 0, "", ("93.184.216.34", 0)),  # example.com — public, OK
        ]

    monkeypatch.setattr(_socket, "getaddrinfo", _mixed)
    reject_private_ip("example.com")


def test_reject_private_ip_allows_public_ipv4(monkeypatch: pytest.MonkeyPatch) -> None:
    """Public IPv4 (example.com's address) is allowed through."""
    _stub_getaddrinfo(monkeypatch, "93.184.216.34")
    reject_private_ip("example.com")


def test_reject_private_ip_allows_public_ipv6(monkeypatch: pytest.MonkeyPatch) -> None:
    """Public IPv6 (Google DNS 2001:4860:4860::8888) is allowed through."""
    _stub_getaddrinfo(monkeypatch, "2001:4860:4860::8888", family=10)
    reject_private_ip("dns.google")


# ── Story 7 RED tests: MIME cross-check ────────────────────────────────────
#
# These fail against current code. They drive the Story 7 implementation:
# fetch_url should accept an optional `expected_mime_prefix` parameter and
# raise InvalidMimeTypeError when the response body's first bytes don't
# match the declared image type. Pillow's format-detect on the first ~512
# bytes is the intended sniff implementation.


@pytest.mark.asyncio
async def test_fetch_url_rejects_mime_mismatch_when_collection_constrains_type(
    mock_httpx_stream: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A response served as image/jpeg whose bytes are not a JPEG raises.

    Currently fails — fetch_url has no MIME cross-check. Story 7 adds the
    optional `expected_mime_prefix` kwarg + Pillow-based byte sniffing.
    """
    _stub_getaddrinfo(monkeypatch, "93.184.216.34")
    mock_httpx_stream["headers"] = {"content-type": "image/jpeg"}
    # Plain ASCII — definitely not a JPEG
    mock_httpx_stream["chunks"] = [b"not a real jpeg payload, just text"]

    # Kwarg via **dict keeps mypy clean. RED today: TypeError propagates
    # because the kwarg doesn't exist. GREEN after Story 7: kwarg is consumed,
    # bytes are sniffed, InvalidMimeTypeError is raised and caught here.
    story_7_kwargs: dict[str, str] = {"expected_mime_prefix": "image/"}
    with pytest.raises(InvalidMimeTypeError, match="image/jpeg"):
        await fetch_url(
            "https://example.com/photo.jpg",
            max_bytes=1024,
            **story_7_kwargs,
        )


@pytest.mark.asyncio
async def test_fetch_url_accepts_matching_mime_when_bytes_match_header(
    mock_httpx_stream: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """An image/png header + actual PNG bytes pass the MIME cross-check.

    Currently fails (no kwarg). Story 7 implementation: when bytes parse as
    the claimed format, fetch_url returns normally.
    """
    import io as _io

    from PIL import Image as _PILImage

    buf = _io.BytesIO()
    _PILImage.new("RGB", (4, 4), (0, 0, 255)).save(buf, format="PNG")
    png_bytes = buf.getvalue()

    _stub_getaddrinfo(monkeypatch, "93.184.216.34")
    mock_httpx_stream["headers"] = {"content-type": "image/png"}
    mock_httpx_stream["chunks"] = [png_bytes]

    # Today: TypeError (kwarg doesn't exist) — that IS the RED failure.
    # After Story 7: kwarg accepted, bytes pass MIME sniff, function returns normally.
    story_7_kwargs: dict[str, str] = {"expected_mime_prefix": "image/"}
    content, name = await fetch_url(
        "https://example.com/picture.png",
        max_bytes=4096,
        **story_7_kwargs,
    )
    assert content == png_bytes
    assert name == "picture.png"


# ── Story 7 RED test: opt-out (no kwarg = current behavior preserved) ───────


@pytest.mark.asyncio
async def test_fetch_url_skips_mime_check_when_no_expectation_given(
    mock_httpx_stream: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without `expected_mime_prefix`, fetch_url's behavior is unchanged.

    Ensures Story 7 is additive — callers that don't pass the new kwarg get
    today's semantics (header-only trust).
    """
    _stub_getaddrinfo(monkeypatch, "93.184.216.34")
    mock_httpx_stream["headers"] = {"content-type": "image/jpeg"}
    mock_httpx_stream["chunks"] = [b"not a jpeg"]

    content, name = await fetch_url("https://example.com/x.jpg", max_bytes=1024)
    assert content == b"not a jpeg"
    assert name == "x.jpg"
