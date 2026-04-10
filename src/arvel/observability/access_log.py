"""ASGI middleware that logs every HTTP request/response with duration.

Produces a single structured log event per request:

    http_request method=GET path=/api/users status=200 duration_ms=12.34

The middleware captures request details at entry and response status at exit,
measuring wall-clock time with ``time.monotonic()``.  It sits outside the
application middleware stack so it captures the full request lifecycle
including all other middleware.

Enable/disable via ``OBSERVABILITY_ACCESS_LOG_ENABLED`` (default ``True``).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from arvel.logging import Log

if TYPE_CHECKING:
    from collections.abc import MutableMapping

    from starlette.types import ASGIApp, Receive, Scope, Send

logger = Log.named("arvel.access")


class AccessLogMiddleware:
    """Pure ASGI middleware — logs method, path, status code, and duration."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method: str = scope.get("method", "?")
        path: str = scope.get("path", "/")
        query: str = scope.get("query_string", b"").decode("latin-1")
        full_path = f"{path}?{query}" if query else path

        start = time.monotonic()
        status_code = 500

        async def send_wrapper(message: MutableMapping[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.monotonic() - start) * 1000

            log_fn = logger.info
            if status_code >= 500:
                log_fn = logger.error
            elif status_code >= 400:
                log_fn = logger.warning

            log_fn(
                "http_request",
                method=method,
                path=full_path,
                status=status_code,
                duration_ms=round(duration_ms, 2),
            )
