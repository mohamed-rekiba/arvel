"""Request ID propagation — ASGI middleware + contextvars.

Also seeds the generic ``Context`` store so service providers can enrich
the request context with additional keys (``tenant_id``, ``user_id``, …)
and have them flow into logs, error responses, and queued jobs
automatically.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import TYPE_CHECKING

from arvel.context.context_store import Context

if TYPE_CHECKING:
    from collections.abc import MutableMapping
    from typing import Any

    from starlette.types import ASGIApp, Receive, Scope, Send

request_id_var: ContextVar[str] = ContextVar("request_id", default="")

_HEADER = b"x-request-id"
_SCOPE_KEY = "arvel_request_id"
SCOPE_CONTEXT_KEY = "arvel_context"


def get_request_id() -> str:
    """Return the current request ID from the ContextVar."""
    return request_id_var.get()


def _extract_request_id(headers: list[tuple[bytes, bytes]]) -> str | None:
    for key, value in headers:
        if key.lower() == _HEADER:
            raw = value.decode("latin-1")
            try:
                uuid.UUID(raw)
                return raw
            except ValueError:
                return None
    return None


class RequestIdMiddleware:
    """Pure ASGI middleware that generates/propagates X-Request-ID.

    - Extracts X-Request-ID from incoming headers (validates as UUID)
    - Generates a new UUID7 if missing or invalid (time-ordered, sortable)
    - Stores in ContextVar **and** ``Context`` store for unified propagation
    - Injects X-Request-ID into response headers
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = scope.get("headers", [])
        rid = _extract_request_id(headers) or str(uuid.uuid7())
        scope[_SCOPE_KEY] = rid
        token = request_id_var.set(rid)
        Context.add("request_id", rid)

        async def send_with_request_id(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                existing_headers = list(message.get("headers", []))
                existing_headers.append((_HEADER, rid.encode("latin-1")))
                message = {**message, "headers": existing_headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id_var.reset(token)
