"""Login-throttle middleware (FR-028-31, closes FB-027-012).

Tracks failed login attempts keyed on ``(email, ip)``.  After
``max_attempts`` failures within ``window_seconds``, the middleware
returns a 429 with a ``Retry-After`` header without touching the handler.

Successful logins (2xx from the handler) clear the counter so legitimate
users are not permanently locked out.

This middleware is ASGI-native and intercepts only POST requests to the
configured ``login_path`` so it adds no overhead to any other route.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import cast

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_DEFAULT_LOGIN_PATH = "/api/auth/login"
_DEFAULT_MAX_ATTEMPTS = 5
_DEFAULT_WINDOW = 60  # seconds
_HTTP_ERROR_MIN = 400
_HTTP_ERROR_MAX = 600
_HTTP_SUCCESS_MAX = 300


class ThrottleLoginMiddleware:
    """ASGI-native login-throttle middleware.

    Keyed on ``(email, ip)`` to avoid blocking one user's email from
    multiple IPs when only a single IP is the attacker.

    Parameters
    ----------
    app:
        The next ASGI application in the stack.
    login_path:
        The exact path to intercept. Defaults to ``/api/auth/login``.
    max_attempts:
        Number of allowed failed attempts before 429 is returned.
    window_seconds:
        Sliding window duration in seconds.
    key_fn:
        Optional override for the rate-limit key: ``(email, ip) -> str``.
        Defaults to ``"throttle:login:{email}:{ip}"``.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        login_path: str = _DEFAULT_LOGIN_PATH,
        max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
        window_seconds: int = _DEFAULT_WINDOW,
        key_fn: Callable[[str, str], str] | None = None,
    ) -> None:
        self._app = app
        self._login_path = login_path
        self._max = max_attempts
        self._window = window_seconds
        self._key_fn: Callable[[str, str], str] = key_fn or _default_key
        # Internal counter store: key -> (count, expires_at_monotonic)
        self._counters: dict[str, tuple[int, float]] = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        path = scope.get("path", "")

        if method != "POST" or path != self._login_path:
            await self._app(scope, receive, send)
            return

        # Buffer the full request body so we can both inspect it and replay it.
        body_events: list[Message] = []
        full_body = b""
        while True:
            event: Message = await receive()
            body_events.append(event)
            full_body += bytes(event.get("body", b""))
            if not event.get("more_body", False):
                break

        email = _parse_email(full_body)
        ip = _client_ip(scope)
        key = self._key_fn(email, ip)

        # Pre-flight check: already at threshold?
        if self._get_count(key) >= self._max:
            resp = _too_many_response(self._window)
            await resp(scope, receive, send)
            return

        # Replay the buffered body to the downstream app.
        body_iter = iter(body_events)

        async def replay_receive() -> Message:
            try:
                return next(body_iter)
            except StopIteration:
                return {"type": "http.disconnect"}

        status_code, resp_headers, resp_body = await _capture_response(
            self._app, scope, replay_receive
        )

        if _HTTP_ERROR_MIN <= status_code < _HTTP_ERROR_MAX:
            self._increment(key)
        elif status_code < _HTTP_SUCCESS_MAX:
            self._reset(key)

        await _replay_response(send, status_code, resp_headers, resp_body)

    # ── counter helpers ───────────────────────────────────────────────────────

    def _get_count(self, key: str) -> int:
        count, expires_at = self._counters.get(key, (0, 0.0))
        if time.monotonic() >= expires_at:
            return 0
        return count

    def _increment(self, key: str) -> int:
        now = time.monotonic()
        count, expires_at = self._counters.get(key, (0, 0.0))
        if now >= expires_at:
            self._counters[key] = (1, now + self._window)
            return 1
        new_count = count + 1
        self._counters[key] = (new_count, expires_at)
        return new_count

    def _reset(self, key: str) -> None:
        self._counters.pop(key, None)


# ── helpers ───────────────────────────────────────────────────────────────────


def _default_key(email: str, ip: str) -> str:
    return f"throttle:login:{email}:{ip}"


def _parse_email(body: bytes) -> str:
    try:
        data: object = json.loads(body.decode("utf-8"))
        if isinstance(data, dict):
            # Cast to typed dict so pyright can narrow .get() return type.
            typed = cast("dict[str, object]", data)
            raw = typed.get("email")
            if isinstance(raw, str):
                return raw.strip().lower()
    except Exception:  # noqa: BLE001
        return ""
    return ""


def _client_ip(scope: Scope) -> str:
    client = scope.get("client")
    if client and client[0]:
        return str(client[0])
    return "unknown"


def _too_many_response(window_seconds: int) -> JSONResponse:
    return JSONResponse(
        content={
            "error": {
                "code": "TOO_MANY_REQUESTS",
                "message": "Too many failed login attempts. Please try again later.",
            }
        },
        status_code=429,
        headers={"Retry-After": str(window_seconds)},
    )


async def _capture_response(
    app: ASGIApp,
    scope: Scope,
    receive: Receive,
) -> tuple[int, list[tuple[bytes, bytes]], bytes]:
    status_code = 200
    headers: list[tuple[bytes, bytes]] = []
    body_chunks: list[bytes] = []

    async def capture_send(message: Message) -> None:
        nonlocal status_code
        if message["type"] == "http.response.start":
            status_code = int(message["status"])
            headers.extend(message.get("headers", []))
        elif message["type"] == "http.response.body":
            body_chunks.append(bytes(message.get("body", b"")))

    await app(scope, receive, capture_send)
    return status_code, headers, b"".join(body_chunks)


async def _replay_response(
    send: Send,
    status_code: int,
    headers: list[tuple[bytes, bytes]],
    body: bytes,
) -> None:
    await send({"type": "http.response.start", "status": status_code, "headers": headers})
    await send({"type": "http.response.body", "body": body, "more_body": False})


__all__ = ["ThrottleLoginMiddleware"]
