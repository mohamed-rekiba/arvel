"""Signed route middleware — validates HMAC-SHA256 signatures on requests.

Attach to routes via ``middleware=["signed"]`` to require valid signatures.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.responses import JSONResponse

from arvel.http.exceptions import InvalidSignatureError

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

    from arvel.http.url import UrlGenerator


class SignedRouteMiddleware:
    """ASGI middleware that rejects requests without a valid signed URL.

    Validates the ``signature`` query parameter using the configured
    ``UrlGenerator``. Returns 403 with Problem Details on failure.
    """

    def __init__(self, app: ASGIApp, *, url_generator: UrlGenerator) -> None:
        self.app = app
        self._url_generator = url_generator

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        query_string = scope.get("query_string", b"").decode()
        full_url = f"{path}?{query_string}" if query_string else path

        try:
            self._url_generator.validate_signature(full_url)
        except InvalidSignatureError as exc:
            response = JSONResponse(
                status_code=403,
                content={
                    "type": "about:blank",
                    "title": "Forbidden",
                    "status": 403,
                    "detail": str(exc.detail),
                },
                media_type="application/problem+json",
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
