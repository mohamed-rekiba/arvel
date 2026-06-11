"""Login-throttle middleware.

Tracks failed login attempts keyed on ``(email, ip)``. After
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
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast, runtime_checkable

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from arvel.auth.config import AuthConfig
from arvel.contracts.middleware import GlobalMiddleware

if TYPE_CHECKING:
    from fastapi import FastAPI

    from arvel.container import Container

_DEFAULT_LOGIN_PATH = "/api/auth/login"
_DEFAULT_MAX_ATTEMPTS = 5
_DEFAULT_WINDOW = 60  # seconds
_HTTP_UNAUTHORIZED = 401
_HTTP_SUCCESS_MAX = 300


@runtime_checkable
class LoginAttemptStore(Protocol):
    """Failed-login counter backing the throttle.

    Three ops: peek the count, bump it on a failure, clear it on success.
    The default is process-local; pass a shared implementation
    (:class:`CacheLoginAttemptStore`) to make the limit hold across workers.
    """

    async def count(self, key: str) -> int: ...
    async def increment(self, key: str, *, window_seconds: int) -> int: ...
    async def reset(self, key: str) -> None: ...


class InMemoryLoginAttemptStore:
    """Process-local counter. Fine for dev, tests, single-process apps."""

    def __init__(self) -> None:
        self._counters: dict[str, tuple[int, float]] = {}

    async def count(self, key: str) -> int:
        count, expires_at = self._counters.get(key, (0, 0.0))
        if time.monotonic() >= expires_at:
            return 0
        return count

    async def increment(self, key: str, *, window_seconds: int) -> int:
        now = time.monotonic()
        count, expires_at = self._counters.get(key, (0, 0.0))
        if now >= expires_at:
            self._counters[key] = (1, now + window_seconds)
            return 1
        new_count = count + 1
        self._counters[key] = (new_count, expires_at)
        return new_count

    async def reset(self, key: str) -> None:
        self._counters.pop(key, None)


class CacheLoginAttemptStore:
    """Cache-backed counter — shared across workers when the cache is Redis.

    Continued failures extend the lockout (the TTL resets on each hit), which
    is the behavior you want against a sustained attack. The peek/increment
    isn't atomic, so under a burst the count can lag by a few — acceptable for a
    throttle.
    """

    async def count(self, key: str) -> int:
        from arvel.facades.cache import Cache  # noqa: PLC0415

        return _coerce_count(await Cache.get(key, 0))

    async def increment(self, key: str, *, window_seconds: int) -> int:
        from arvel.facades.cache import Cache  # noqa: PLC0415

        new_count = _coerce_count(await Cache.get(key, 0)) + 1
        await Cache.put(key, new_count, ttl=window_seconds)
        return new_count

    async def reset(self, key: str) -> None:
        from arvel.facades.cache import Cache  # noqa: PLC0415

        await Cache.forget(key)


def _coerce_count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


@dataclass(frozen=True, slots=True)
class ThrottleLoginConfig:
    """Tuning for :class:`ThrottleLoginMiddleware`."""

    login_path: str = _DEFAULT_LOGIN_PATH
    max_attempts: int = _DEFAULT_MAX_ATTEMPTS
    window_seconds: int = _DEFAULT_WINDOW
    key_fn: Callable[[str, str], str] | None = None
    store: LoginAttemptStore | None = None


class ThrottleLoginMiddleware(GlobalMiddleware):
    """ASGI-native login-throttle middleware.

    Keyed on ``(email, ip)`` to avoid blocking one user's email from
    multiple IPs when only a single IP is the attacker.

    Tuning (path, limits, key function, counter backend) comes from
    :class:`ThrottleLoginConfig`. Pass a config with
    :class:`CacheLoginAttemptStore` to share the limit across workers.
    """

    def __init__(self, app: ASGIApp, config: ThrottleLoginConfig | None = None) -> None:
        cfg = config or ThrottleLoginConfig()
        self._app = app
        self._login_path = cfg.login_path
        self._max = cfg.max_attempts
        self._window = cfg.window_seconds
        self._key_fn: Callable[[str, str], str] = cfg.key_fn or _default_key
        self._store: LoginAttemptStore = cfg.store or InMemoryLoginAttemptStore()

    @classmethod
    def boot(cls, app: FastAPI, container: Container) -> None:
        """Mount when auth is registered and rate limiting is enabled."""
        # No default AuthConfig exists (it needs a guard name), so only mount
        # when AuthServiceProvider explicitly bound one.
        if not container.bound(AuthConfig):
            return
        config = container.make(AuthConfig)
        rate_limit = config.rate_limit
        if not rate_limit.enabled:
            return
        prefix = config.routes.prefix.rstrip("/")
        app.add_middleware(
            cls,
            config=ThrottleLoginConfig(
                login_path=f"{prefix}/login",
                max_attempts=rate_limit.max_attempts,
                window_seconds=rate_limit.decay_seconds,
                # Cache-backed by default so the limit holds across workers
                # (Redis in prod). The in-memory store is only the bare
                # constructor fallback for tests / single-process use.
                store=CacheLoginAttemptStore(),
            ),
        )

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
        if await self._store.count(key) >= self._max:
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

        # Only bad credentials (401) count toward the lockout. A 422 (email not
        # verified), 403 (suspended), or 5xx isn't a guessing attempt and must
        # not lock the account out.
        if status_code == _HTTP_UNAUTHORIZED:
            await self._store.increment(key, window_seconds=self._window)
        elif status_code < _HTTP_SUCCESS_MAX:
            await self._store.reset(key)

        await _replay_response(send, status_code, resp_headers, resp_body)


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


__all__ = [
    "CacheLoginAttemptStore",
    "InMemoryLoginAttemptStore",
    "LoginAttemptStore",
    "ThrottleLoginConfig",
    "ThrottleLoginMiddleware",
]
