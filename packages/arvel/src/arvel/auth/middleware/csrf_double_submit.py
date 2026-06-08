"""CSRF double-submit middleware for the auth cookie flow.

Reads the ``_csrf`` cookie set by the login endpoint and compares it to the
``X-CSRF-TOKEN`` (or ``X-XSRF-TOKEN``) request header, timing-safe. Mismatch
raises the shared :class:`arvel.http.exceptions.CsrfMismatchException` (419).

ASGI-native (not ``BaseHTTPMiddleware``) so framework exception handlers see
the error through the normal handler chain.

Exempt paths (checked with ``startswith``): login, register, forgot-password,
reset-password, and the verify-email GET — these endpoints either create the
cookie or don't need CSRF protection.
"""

from __future__ import annotations

from collections.abc import Sequence

from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from arvel.http.exceptions import CsrfMismatchException
from arvel.support.secure_compare import constant_time_equals

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
_DEFAULT_CSRF_COOKIE = "_csrf"
_DEFAULT_CSRF_HEADER = "X-CSRF-TOKEN"
_XSRF_HEADER = "X-XSRF-TOKEN"
_DEFAULT_EXEMPT: tuple[str, ...] = (
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/auth/verify/",
    "/auth/login",
    "/auth/register",
    "/auth/forgot-password",
    "/auth/reset-password",
    "/auth/verify/",
)


class CsrfDoubleSubmitMiddleware:
    """ASGI-native double-submit CSRF middleware for the auth cookie flow.

    Add to the Starlette app stack, not as a route-level middleware, so it
    intercepts every state-mutating request before the route handler runs.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        csrf_cookie: str = _DEFAULT_CSRF_COOKIE,
        csrf_header: str = _DEFAULT_CSRF_HEADER,
        exempt_paths: Sequence[str] | None = None,
    ) -> None:
        self._app = app
        self._csrf_cookie = csrf_cookie
        self._csrf_header = csrf_header
        self._exempt: tuple[str, ...] = (
            tuple(exempt_paths) if exempt_paths is not None else _DEFAULT_EXEMPT
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        path = scope.get("path", "")

        # Parse headers once.
        headers: list[tuple[bytes, bytes]] = scope.get("headers", [])

        if method in _SAFE_METHODS or any(path.startswith(p) for p in self._exempt):
            await self._app(scope, receive, send)
            return

        # Bearer-token requests are CSRF-immune: an attacker cannot read the
        # bearer from a cross-origin context, so forged requests can't carry it.
        auth_header = _find_header(headers, b"authorization")
        if auth_header and auth_header.lower().startswith("bearer ") and auth_header[7:].strip():
            await self._app(scope, receive, send)
            return

        # Parse cookies from the request headers.
        cookie_header = _find_header(headers, b"cookie")
        cookies = _parse_cookies(cookie_header)
        csrf_cookie_value = cookies.get(self._csrf_cookie)

        # Find the CSRF header (header names are lowercase in ASGI). Accept the
        # X-XSRF-TOKEN alias too — Axios and friends send it from the XSRF cookie.
        csrf_header_value = _find_header(
            headers, self._csrf_header.lower().encode("latin-1")
        ) or _find_header(headers, _XSRF_HEADER.lower().encode("latin-1"))

        if (
            not csrf_cookie_value
            or not csrf_header_value
            or not constant_time_equals(csrf_cookie_value, csrf_header_value)
        ):
            exc = CsrfMismatchException("CSRF token mismatch.")
            response = _error_response(exc)
            await response(scope, receive, send)
            return

        await self._app(scope, receive, send)


# ── helpers ──────────────────────────────────────────────────────────────────


def _find_header(headers: list[tuple[bytes, bytes]], name: bytes) -> str | None:
    for header_name, header_value in headers:
        if header_name.lower() == name:
            return header_value.decode("latin-1")
    return None


def _parse_cookies(cookie_header: str | None) -> dict[str, str]:
    if not cookie_header:
        return {}
    cookies: dict[str, str] = {}
    for part in cookie_header.split(";"):
        key, _, value = part.strip().partition("=")
        if key:
            cookies[key.strip()] = value.strip()
    return cookies


def _error_response(exc: CsrfMismatchException) -> Response:
    from starlette.responses import JSONResponse  # noqa: PLC0415

    return JSONResponse(
        content=exc.to_dict(),
        status_code=exc.status_code,
    )


# Re-export the shared exception so callers can import it alongside the middleware.
__all__ = ["CsrfDoubleSubmitMiddleware", "CsrfMismatchException"]
