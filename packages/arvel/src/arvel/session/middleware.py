"""StartSession middleware — pure ASGI middleware for session management.

Pure ASGI implementation — avoids Starlette's BaseHTTPMiddleware, which
buffers streaming responses and causes Content-Length mismatches.
"""

from __future__ import annotations

import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from arvel.session.data import SessionData
from arvel.session.store import SessionStore


class StartSession:
    """ASGI middleware that loads and persists sessions.

    Added to a named middleware group (e.g. "web") — not globally applied.
    Can be used with Starlette's middleware list:

        middleware = [(StartSession, {"store": store, "lifetime": 120})]
    """

    def __init__(
        self,
        app: ASGIApp,
        store: SessionStore,
        lifetime: int = 7200,
        cookie_name: str = "arvel_session",
    ) -> None:
        self._app = app
        self._store = store
        self._lifetime = lifetime
        self._cookie_name = cookie_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        headers_list: list[tuple[bytes, bytes]] = scope.get("headers", [])
        cookie_header = ""
        for name, value in headers_list:
            if name.lower() == b"cookie":
                cookie_header = value.decode("latin-1")
                break

        session_id = _parse_cookie(cookie_header, self._cookie_name) or uuid.uuid4().hex

        raw = await self._store.read(session_id)
        raw["_session_id"] = session_id
        session = SessionData(raw)
        session.finalize_flash()

        # Starlette 1.x keeps scope["state"] as a plain dict; Request.state wraps
        # it lazily. Write through the dict so attribute access works from handlers.
        scope.setdefault("state", {})
        scope["state"]["session"] = session

        cookie_value = (
            f"{self._cookie_name}={session.get_id()}; "
            f"Max-Age={self._lifetime}; Path=/; HttpOnly; SameSite=Lax"
        )

        async def send_with_session(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append("Set-Cookie", cookie_value)
            elif message["type"] == "http.response.body" and not message.get("more_body", False):
                await send(message)
                await self._store.write(session.get_id(), session.to_dict(), self._lifetime)
                return
            await send(message)

        await self._app(scope, receive, send_with_session)


def _parse_cookie(cookie_header: str, name: str) -> str:
    for part in cookie_header.split(";"):
        key, _, value = part.strip().partition("=")
        if key.strip() == name:
            return value.strip()
    return ""


__all__ = ["StartSession"]
