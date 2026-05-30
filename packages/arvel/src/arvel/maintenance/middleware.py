"""Maintenance-mode ASGI middleware."""

from __future__ import annotations

import secrets
import time
from typing import TYPE_CHECKING
from urllib.parse import parse_qs

from starlette.responses import PlainTextResponse

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

    from arvel.maintenance.manager import MaintenanceModeManager


_BYPASS_COOKIE = "arvel_bypass"
_CACHE_TTL_SECONDS = 1.0


class MaintenanceModeMiddleware:
    """Return 503 for HTTP requests when the maintenance marker is present.

    The marker file is read at most once per second per worker (TTL cache) to
    avoid filesystem hot-loop overhead.

    Behaviour summary:

    - No marker → pass through.
    - Marker + bypass cookie matching the marker's ``secret`` → pass through.
    - Marker + ``?bypass=<secret>`` query param matching → set the bypass
      cookie and pass through.
    - Marker + no valid bypass → respond ``503`` with optional ``Retry-After``
      and ``Refresh`` headers.
    """

    def __init__(self, app: ASGIApp, manager: MaintenanceModeManager) -> None:
        self._app: ASGIApp = app
        self._manager: MaintenanceModeManager = manager
        self._cached_state: tuple[float, bool, str | None, int | None, int | None] | None = None

    def _read_state(self) -> tuple[bool, str | None, int | None, int | None]:
        """Return (is_down, secret, retry, refresh), TTL-cached."""
        now = time.monotonic()
        if self._cached_state is not None:
            ts, is_down, secret, retry, refresh = self._cached_state
            if now - ts < _CACHE_TTL_SECONDS:
                return is_down, secret, retry, refresh
        marker = self._manager.read_marker()
        if marker is None:
            self._cached_state = (now, False, None, None, None)
            return False, None, None, None
        self._cached_state = (now, True, marker.secret, marker.retry, marker.refresh)
        return True, marker.secret, marker.retry, marker.refresh

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        is_down, secret, retry, refresh = self._read_state()
        if not is_down or secret is None:
            await self._app(scope, receive, send)
            return

        if self._has_valid_cookie(scope, secret):
            await self._app(scope, receive, send)
            return

        query_secret = self._extract_query_bypass(scope)
        if query_secret is not None and secrets.compare_digest(query_secret, secret):
            await self._send_pass_through_with_cookie(scope, receive, send, secret)
            return

        await self._send_503(send, retry=retry, refresh=refresh)

    @staticmethod
    def _has_valid_cookie(scope: Scope, secret: str) -> bool:
        cookies = _parse_cookies(scope)
        provided = cookies.get(_BYPASS_COOKIE)
        if provided is None:
            return False
        return secrets.compare_digest(provided, secret)

    @staticmethod
    def _extract_query_bypass(scope: Scope) -> str | None:
        raw = scope.get("query_string", b"")
        if not isinstance(raw, (bytes, bytearray)) or not raw:
            return None
        params: dict[str, list[str]] = parse_qs(raw.decode("latin-1"))
        values = params.get("bypass")
        if not values:
            return None
        return values[0]

    async def _send_pass_through_with_cookie(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        secret: str,
    ) -> None:
        is_https = scope.get("scheme") == "https"
        cookie_attrs = [
            f"{_BYPASS_COOKIE}={secret}",
            "Path=/",
            "HttpOnly",
            "SameSite=Lax",
        ]
        if is_https:
            cookie_attrs.append("Secure")
        cookie_header_value = "; ".join(cookie_attrs).encode("latin-1")

        async def _send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append((b"set-cookie", cookie_header_value))
                message = {**message, "headers": headers}
            await send(message)

        await self._app(scope, receive, _send_wrapper)

    async def _send_503(
        self,
        send: Send,
        *,
        retry: int | None,
        refresh: int | None,
    ) -> None:
        headers: dict[str, str] = {}
        if retry is not None:
            headers["Retry-After"] = str(retry)
        if refresh is not None:
            headers["Refresh"] = str(refresh)
        response = PlainTextResponse(
            "App is down for maintenance.",
            status_code=503,
            headers=headers,
        )
        await response(
            {"type": "http"},
            _empty_receive,
            send,
        )


async def _empty_receive() -> Message:
    return {"type": "http.disconnect"}


def _parse_cookies(scope: Scope) -> dict[str, str]:
    cookies: dict[str, str] = {}
    headers: list[tuple[bytes, bytes]] = scope.get("headers") or []
    for name, value in headers:
        if name == b"cookie":
            for pair in value.decode("latin-1").split(";"):
                if "=" not in pair:
                    continue
                key, raw_val = pair.strip().split("=", 1)
                cookies[key] = raw_val
            break
    return cookies
