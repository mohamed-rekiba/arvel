"""SecurityHeadersMiddleware — pure-ASGI HTTP security headers.

Injects four headers on every HTTP response:

- ``Strict-Transport-Security`` — HSTS with preload.
- ``X-Content-Type-Options: nosniff`` — prevents MIME-type sniffing.
- ``Referrer-Policy: strict-origin-when-cross-origin`` — limits referrer leakage.
- ``Content-Security-Policy`` — defaults to a tight policy with
 ``frame-ancestors 'none'`` (no clickjacking); override via constructor.

All headers use ``setdefault`` semantics: if the handler already sent a header
(e.g. a route that returns a custom CSP), the middleware does not overwrite it.

Non-HTTP scopes (WebSocket, lifespan) pass through unmodified.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_DEFAULT_HSTS_MAX_AGE: int = 31_536_000  # 1 year
_DEFAULT_CSP: str = "default-src 'self'; frame-ancestors 'none'; form-action 'self'"
_DEFAULT_REFERRER_POLICY: str = "strict-origin-when-cross-origin"


class SecurityHeadersMiddleware:
    """Add HTTP security headers to every response.

    All values are configurable via constructor kwargs.  Omitting a kwarg
    uses the opinionated default.  Pass ``csp=None`` to suppress the CSP
    header entirely (not recommended for production).

    ``path_csp_overrides`` maps path prefixes to a CSP string (or ``None``
    to omit the header entirely for that path).  Longest matching prefix wins.
    Useful for serving Swagger UI or other CDN-backed pages under a different
    policy without loosening the global default.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        hsts_max_age: int = _DEFAULT_HSTS_MAX_AGE,
        csp: str | None = _DEFAULT_CSP,
        referrer_policy: str = _DEFAULT_REFERRER_POLICY,
        path_csp_overrides: dict[str, str | None] | None = None,
    ) -> None:
        self._app = app
        self._hsts = f"max-age={hsts_max_age}; includeSubDomains; preload"
        self._csp = csp
        self._referrer_policy = referrer_policy
        # Sort by length descending so the most-specific prefix matches first.
        self._path_csp_overrides: list[tuple[str, str | None]] = sorted(
            (path_csp_overrides or {}).items(),
            key=lambda kv: len(kv[0]),
            reverse=True,
        )

    def _csp_for_path(self, path: str) -> str | None:
        for prefix, override in self._path_csp_overrides:
            if path.startswith(prefix):
                return override
        return self._csp

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        effective_csp = self._csp_for_path(path)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("Strict-Transport-Security", self._hsts)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("Referrer-Policy", self._referrer_policy)
                if effective_csp is not None:
                    headers.setdefault("Content-Security-Policy", effective_csp)
            await send(message)

        await self._app(scope, receive, send_with_headers)


__all__ = ["SecurityHeadersMiddleware"]
