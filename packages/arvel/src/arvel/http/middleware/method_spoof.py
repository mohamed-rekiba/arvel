"""``MethodSpoofMiddleware`` — HTML form ``_method`` override.

Laravel's HTML forms can only emit GET/POST. Embedding ``<input type="hidden"
name="_method" value="PUT">`` in a POST form lets the server route the request
to a PUT handler. This middleware rewrites ``scope["method"]`` on POSTs that
carry a recognised spoofed verb in the URL-encoded form body, before route
matching runs.

Mounted as an ASGI middleware (not a per-route ``arvel.http.Middleware``)
because route matching happens before per-route middlewares fire — a
per-route hook would arrive after the method has already been used to pick
the handler.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from urllib.parse import parse_qs

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_SPOOFABLE_VERBS = frozenset({"PUT", "PATCH", "DELETE"})
_FORM_CONTENT_TYPES = (
    "application/x-www-form-urlencoded",
    "multipart/form-data",
)


class MethodSpoofMiddleware:
    """Rewrite POST + ``_method=<VERB>`` form body to the requested verb.

    Only POST requests with a form Content-Type are inspected. Other methods,
    JSON bodies, and unknown ``_method`` values pass through untouched.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method", "").upper() != "POST":
            await self._app(scope, receive, send)
            return

        content_type = _header(scope, b"content-type") or ""
        if not any(ct in content_type.lower() for ct in _FORM_CONTENT_TYPES):
            await self._app(scope, receive, send)
            return

        body, replay_receive = await _buffer_body(receive)
        spoofed = _extract_method(body, content_type)
        if spoofed in _SPOOFABLE_VERBS:
            # Shallow-copy scope so we don't mutate the caller's dict.
            scope = {**scope, "method": spoofed}
        await self._app(scope, replay_receive, send)


def _header(scope: Scope, name: bytes) -> str | None:
    """Return a request header value as a UTF-8 string, or None if absent."""
    headers: list[tuple[bytes, bytes]] = scope.get("headers", []) or []
    for key, value in headers:
        if key == name:
            return value.decode("latin-1")
    return None


async def _buffer_body(receive: Receive) -> tuple[bytes, Receive]:
    """Drain the ASGI ``http.request`` stream into a single bytes buffer.

    Returns ``(body, replay_receive)`` where ``replay_receive`` re-emits the
    same body to the downstream app so the handler sees an unchanged stream.
    """
    chunks: list[bytes] = []
    more = True
    while more:
        message = await receive()
        if message["type"] != "http.request":
            chunks.append(b"")
            more = False
            continue
        chunks.append(message.get("body", b"") or b"")
        more = bool(message.get("more_body", False))
    body = b"".join(chunks)

    sent = False

    async def replay() -> Message:
        nonlocal sent
        if sent:
            # ASGI spec: after a complete request, the server signals
            # disconnect. Honour that for well-behaved downstreams.
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return body, replay


def _extract_method(body: bytes, content_type: str) -> str | None:
    """Pull ``_method`` from a form body. Returns None when not present."""
    if "multipart/form-data" in content_type.lower():
        return _extract_method_multipart(body, content_type)
    try:
        decoded = body.decode("utf-8")
    except UnicodeDecodeError:
        return None
    parsed = parse_qs(decoded, keep_blank_values=False)
    values = parsed.get("_method")
    if not values:
        return None
    return values[0].strip().upper()


def _extract_method_multipart(body: bytes, content_type: str) -> str | None:
    """Best-effort ``_method`` lookup for multipart bodies.

    Avoids pulling in a full multipart parser — we only need a single field.
    Returns None when the boundary or field can't be located cleanly.
    """
    boundary = _multipart_boundary(content_type)
    if boundary is None:
        return None
    marker = b'name="_method"'
    idx = body.find(marker)
    if idx == -1:
        return None
    # Body section starts after the blank line following the headers.
    blank = body.find(b"\r\n\r\n", idx)
    if blank == -1:
        return None
    end = body.find(b"\r\n--" + boundary, blank)
    if end == -1:
        return None
    raw_value = body[blank + 4 : end].strip()
    try:
        return raw_value.decode("utf-8").strip().upper()
    except UnicodeDecodeError:
        return None


def _multipart_boundary(content_type: str) -> bytes | None:
    for raw_part in content_type.split(";"):
        part = raw_part.strip()
        if part.lower().startswith("boundary="):
            value = part.split("=", 1)[1].strip().strip('"')
            return value.encode("latin-1")
    return None


# Keep an unused-import-safe alias for callers that want the ASGI handler shape.
_Caller = Callable[[Scope, Receive, Send], Awaitable[None]]


__all__ = ["MethodSpoofMiddleware"]
