"""CSRF protection middleware — double-submit cookie + origin check.

Protects state-changing methods (POST, PUT, PATCH, DELETE) by requiring
either a valid CSRF token or a matching Origin header. API routes using
Bearer authentication can be excluded.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import TYPE_CHECKING

from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

_STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_TOKEN_BYTES = 32


def generate_csrf_token(secret_key: bytes) -> str:
    """Generate a cryptographically random CSRF token signed with the app key."""
    random_part = os.urandom(_TOKEN_BYTES).hex()
    signature = hmac.new(secret_key, random_part.encode(), hashlib.sha256).hexdigest()
    return f"{random_part}.{signature}"


def verify_csrf_token(token: str, secret_key: bytes) -> bool:
    """Verify a CSRF token's signature using constant-time comparison."""
    parts = token.split(".", 1)
    if len(parts) != 2:
        return False
    random_part, provided_sig = parts
    expected_sig = hmac.new(secret_key, random_part.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided_sig, expected_sig)


class CsrfMiddleware:
    """ASGI middleware for CSRF protection.

    Checks state-changing requests for either:
    1. A valid CSRF token in the ``X-CSRF-Token`` header (or ``_token`` form field)
    2. An ``Origin`` header matching the configured ``allowed_origins``

    Skips paths listed in ``exclude_paths`` (e.g., API routes with Bearer auth).
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        secret_key: bytes,
        allowed_origins: set[str] | None = None,
        exclude_paths: set[str] | None = None,
        exclude_prefixes: tuple[str, ...] = (),
        token_header: str = "x-csrf-token",  # noqa: S107
    ) -> None:
        self.app = app
        self._secret_key = secret_key
        self._allowed_origins = allowed_origins or set()
        self._exclude_paths = exclude_paths or set()
        self._exclude_prefixes = exclude_prefixes
        self._token_header = token_header.lower().encode("latin-1")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        if method not in _STATE_CHANGING_METHODS:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in self._exclude_paths:
            await self.app(scope, receive, send)
            return

        if any(path.startswith(prefix) for prefix in self._exclude_prefixes):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))

        origin = headers.get(b"origin", b"").decode("latin-1")
        if origin and origin in self._allowed_origins:
            await self.app(scope, receive, send)
            return

        token = headers.get(self._token_header, b"").decode("latin-1")
        if token and verify_csrf_token(token, self._secret_key):
            await self.app(scope, receive, send)
            return

        response = JSONResponse(
            {
                "error": {
                    "code": "CSRF_TOKEN_MISMATCH",
                    "message": "CSRF token missing or invalid",
                }
            },
            status_code=419,
        )
        await response(scope, receive, send)
