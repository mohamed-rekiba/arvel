"""HTTP download with SSRF guard.

Resolves the hostname before connecting and rejects private / loopback /
link-local IP addresses. DNS rebinding is a known limitation — the
host is resolved once for the guard, then re-resolved by httpx for the
actual request. Document this caveat for callers that pass arbitrary URLs.
"""

from __future__ import annotations

import ipaddress
import socket
from io import BytesIO
from urllib.parse import urlparse, urlunparse

from arvel_image.media.exceptions import FileTooLargeError, InvalidMimeTypeError, MediaError

_SSRF_REJECT: tuple[str, ...] = (
    "is_private",
    "is_loopback",
    "is_link_local",
    "is_multicast",
    "is_reserved",
    "is_unspecified",
)


def _safe_url(url: str) -> str:
    """Strip userinfo from a URL before logging — credentials don't go in messages."""
    try:
        parts = urlparse(url)
    except ValueError:
        return "<unparseable url>"
    if not parts.username and not parts.password:
        return url
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    netloc = f"{host}{port}"
    return urlunparse(parts._replace(netloc=netloc))


def reject_private_ip(host: str) -> None:
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


async def fetch_url(
    url: str, max_bytes: int, *, expected_mime_prefix: str | None = None
) -> tuple[bytes, str]:
    """Download ``url``, enforce SSRF guard and size cap.

    When ``expected_mime_prefix`` is set (e.g. ``"image/"``), the response
    bytes are sniffed and compared against the server's Content-Type header.
    A mismatch raises :class:`InvalidMimeTypeError`. Callers that don't care
    about content-type integrity can omit the kwarg — behavior is unchanged.

    Returns ``(bytes_content, derived_file_name)``.
    """
    try:
        import httpx  # noqa: PLC0415
    except ImportError as exc:
        msg = (
            "httpx is required to add media from an http(s):// URL. "
            "Install it with: pip install httpx  (or: uv add httpx)."
        )
        raise ImportError(msg) from exc

    parsed = urlparse(url)

    # Allowlist approach — only http/https permitted
    if parsed.scheme not in ("http", "https"):
        msg = f"URL scheme '{parsed.scheme}' is not permitted; only http and https are allowed"
        raise MediaError(msg)

    host = parsed.hostname or ""
    reject_private_ip(host)

    safe = _safe_url(url)

    # Stream the body and abort as soon as we cross max_bytes, so a hostile
    # server can't exhaust memory by sending gigabytes before we'd ever check.
    # Redirects are intentionally not followed — a redirect to a private
    # address would bypass the SSRF guard above. Callers must supply the
    # final URL.
    claimed_content_type: str | None = None
    async with (
        httpx.AsyncClient(follow_redirects=False, timeout=30) as client,
        client.stream("GET", url) as response,
    ):
        response.raise_for_status()
        claimed_content_type = response.headers.get("content-type")
        _reject_oversize_header(safe, response.headers.get("content-length"), max_bytes)

        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > max_bytes:
                msg = (
                    f"Download from {safe!r} exceeds max_bytes={max_bytes} "
                    f"(streamed {total} bytes before abort)"
                )
                raise FileTooLargeError(msg)
            chunks.append(chunk)
        content = b"".join(chunks)

    # MIME cross-check (opt-in via expected_mime_prefix). Catches servers that
    # claim image/jpeg but ship something else — relevant when a collection
    # restricts accepted types and the URL is attacker-controlled.
    if expected_mime_prefix is not None and expected_mime_prefix.startswith("image/"):
        claimed = ""
        if claimed_content_type:
            claimed = claimed_content_type.split(";", 1)[0].strip().lower()
        sniffed = sniff_image_mime(content)
        if not claimed or sniffed != claimed:
            msg = (
                f"MIME mismatch on {safe!r}: server claimed "
                f"{claimed or '<missing>'!r}, Pillow sniff detected {sniffed!r}"
            )
            raise InvalidMimeTypeError(msg)

    # Derive file_name from the URL path; fall back to "download".
    path_part = parsed.path.rstrip("/")
    derived = path_part.split("/")[-1] if path_part else "download"
    return content, derived or "download"


def _reject_oversize_header(url: str, content_length: str | None, max_bytes: int) -> None:
    """Fail fast when the advertised Content-Length already exceeds the cap.

    ``url`` is expected to already be userinfo-stripped (see :func:`_safe_url`).
    """
    if content_length is None:
        return
    try:
        declared = int(content_length)
    except ValueError:
        return
    if declared > max_bytes:
        msg = (
            f"Download from {url!r} exceeds max_bytes={max_bytes} "
            f"(Content-Length header advertised {declared} bytes)"
        )
        raise FileTooLargeError(msg)


def sniff_image_mime(contents: bytes) -> str | None:
    """Return the real image MIME from magic bytes, or ``None`` for non-images.

    Reads only the header — Pillow decodes lazily on ``open()``. Shared by the
    URL fetcher (Content-Type cross-check) and the file adder (extension
    spoofing defense).
    """
    from PIL import Image as PILImage  # noqa: PLC0415

    try:
        with PILImage.open(BytesIO(contents)) as img:
            fmt = img.format
    except Exception:  # noqa: BLE001
        # Pillow raises a wide set on malformed input (UnidentifiedImageError,
        # OSError, ValueError, plus codec-specific quirks). We return None to
        # signal "not a valid image" — the caller decides how to react.
        return None
    if fmt is None:
        return None
    return PILImage.MIME.get(fmt)
