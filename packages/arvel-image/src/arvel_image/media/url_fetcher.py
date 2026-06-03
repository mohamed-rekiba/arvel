"""HTTP download with SSRF guard .

Resolves the hostname before connecting and rejects private/loopback/
link-local IP addresses. DNS rebinding is a known limitation — documented
in the public add_media_from_url docstring.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from arvel_image.media.exceptions import MediaError

_SSRF_REJECT: tuple[str, ...] = (
    "is_private",
    "is_loopback",
    "is_link_local",
    "is_multicast",
    "is_reserved",
    "is_unspecified",
)


def _reject_private_ip(host: str) -> None:
    """Raise :class:`MediaError` if ``host`` resolves to a restricted IP."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        msg = f"SSRF guard: could not resolve host '{host}': {exc}"
        raise MediaError(msg) from exc

    for _fam, _type, _proto, _canon, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        for attr in _SSRF_REJECT:
            if getattr(addr, attr, False):
                msg = f"SSRF guard blocked '{host}' → {ip_str} ({attr})"
                raise MediaError(msg)


async def fetch_url(url: str, max_bytes: int) -> tuple[bytes, str]:
    """Download ``url``, enforce SSRF guard and size cap.

    Returns ``(bytes_content, derived_file_name)``.
    """
    try:
        import httpx  # noqa: PLC0415
    except ImportError as exc:
        msg = "httpx is required for add_media_from_url; install it with: pip install httpx"
        raise ImportError(msg) from exc

    parsed = urlparse(url)

    # Allowlist approach — only http/https permitted
    if parsed.scheme not in ("http", "https"):
        msg = f"URL scheme '{parsed.scheme}' is not permitted; only http and https are allowed"
        raise MediaError(msg)

    host = parsed.hostname or ""
    _reject_private_ip(host)

    # Stream the body and abort as soon as we cross max_bytes, so a hostile
    # server can't exhaust memory by sending gigabytes before we'd ever check.
    # Redirects are intentionally not followed — a redirect to a private
    # address would bypass the SSRF guard above. Callers must supply the
    # final URL.
    async with (
        httpx.AsyncClient(follow_redirects=False, timeout=30) as client,
        client.stream("GET", url) as response,
    ):
        response.raise_for_status()
        _reject_oversize_header(url, response.headers.get("content-length"), max_bytes)

        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > max_bytes:
                msg = f"Download from {url!r} exceeds max_bytes={max_bytes}"
                raise MediaError(msg)
            chunks.append(chunk)
        content = b"".join(chunks)

    # Derive file_name from the URL path; fall back to "download".
    path_part = parsed.path.rstrip("/")
    derived = path_part.split("/")[-1] if path_part else "download"
    return content, derived or "download"


def _reject_oversize_header(url: str, content_length: str | None, max_bytes: int) -> None:
    """Fail fast when the advertised Content-Length already exceeds the cap."""
    if content_length is None:
        return
    try:
        declared = int(content_length)
    except ValueError:
        return
    if declared > max_bytes:
        msg = f"Download from {url!r} exceeds max_bytes={max_bytes}"
        raise MediaError(msg)
