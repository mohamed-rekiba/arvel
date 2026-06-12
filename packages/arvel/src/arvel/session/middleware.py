"""StartSession middleware — pure ASGI middleware for session management.

Pure ASGI implementation — avoids Starlette's BaseHTTPMiddleware, which
buffers streaming responses and causes Content-Length mismatches.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from arvel.config.session_config import SameSite
from arvel.session.data import SessionData
from arvel.session.store import CookieBackedStore, SessionStore


@dataclass(frozen=True, slots=True)
class SessionCookie:
    """Set-Cookie knobs for ``StartSession`` (sourced from ``SessionConfig``)."""

    name: str = "arvel_session"
    lifetime: int = 7200
    secure: bool = False
    same_site: SameSite = SameSite.LAX

    @property
    def force_secure(self) -> bool:
        # SameSite=None is rejected by browsers without Secure, so force it on.
        return self.secure or self.same_site is SameSite.NONE


class StartSession:
    """ASGI middleware that loads and persists sessions.

    Added to a named middleware group (e.g. "web") — not globally applied.
    Can be used with Starlette's middleware list:

        middleware = [(StartSession, {"store": store, "options": SessionCookie(lifetime=120)})]
    """

    def __init__(
        self,
        app: ASGIApp,
        store: SessionStore,
        options: SessionCookie | None = None,
    ) -> None:
        self._app = app
        self._store = store
        self._options = options or SessionCookie()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        store = self._store
        cookie_store: CookieBackedStore | None = (
            store if isinstance(store, CookieBackedStore) else None
        )
        session = await self._load_session(scope, cookie_store)

        # Starlette 1.x keeps scope["state"] as a plain dict; Request.state wraps
        # it lazily. Write through the dict so attribute access works from handlers.
        scope.setdefault("state", {})
        scope["state"]["session"] = session

        async def send_with_session(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append(
                    "Set-Cookie", self._cookie_value(session, cookie_store)
                )
            elif message["type"] == "http.response.body" and not message.get("more_body", False):
                await send(message)
                await self._persist(session, cookie_store)
                return
            await send(message)

        await self._app(scope, receive, send_with_session)

    async def _load_session(
        self, scope: Scope, cookie_store: CookieBackedStore | None
    ) -> SessionData:
        cookie_val = _parse_cookie(_cookie_header(scope), self._options.name)
        if cookie_store is not None:
            raw = await cookie_store.read_from_cookie(cookie_val)
        else:
            session_id = cookie_val or uuid.uuid4().hex
            raw = await self._store.read(session_id)
            raw["_session_id"] = session_id

        session = SessionData(raw)
        session.finalize_flash()
        # Ensure a CSRF token exists so VerifyCsrf and templates can read it.
        session.token()
        return session

    def _cookie_value(self, session: SessionData, cookie_store: CookieBackedStore | None) -> str:
        # Built at response.start — after the handler ran, so a login that calls
        # regenerate() is reflected in the id/payload we send back.
        opts = self._options
        if cookie_store is not None:
            payload = cookie_store.encode(session.to_dict())
        else:
            payload = session.get_id()
        value = (
            f"{opts.name}={payload}; "
            f"Max-Age={opts.lifetime}; Path=/; HttpOnly; SameSite={opts.same_site.cookie_attr}"
        )
        if opts.force_secure:
            value += "; Secure"
        return value

    async def _persist(self, session: SessionData, cookie_store: CookieBackedStore | None) -> None:
        if cookie_store is not None:
            # Self-contained cookie: nothing server-side to write or destroy.
            return
        await self._store.write(session.get_id(), session.to_dict())
        # Drop ids rotated out by regenerate() so the old record can't outlive
        # the new one (session-fixation hygiene).
        for old_id in session.drain_pending_destroy():
            await self._store.destroy(old_id)


def _cookie_header(scope: Scope) -> str:
    headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
    for name, value in headers:
        if name.lower() == b"cookie":
            return value.decode("latin-1")
    return ""


def _parse_cookie(cookie_header: str, name: str) -> str:
    for part in cookie_header.split(";"):
        key, _, value = part.strip().partition("=")
        if key.strip() == name:
            return value.strip()
    return ""


__all__ = ["SessionCookie", "StartSession"]
