"""Locale detection middleware — sets the translator's active locale from Accept-Language."""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

request_locale_var: ContextVar[str] = ContextVar("request_locale", default="en")


def get_request_locale() -> str:
    return request_locale_var.get()


class LocaleMiddleware:
    """ASGI middleware that reads ``Accept-Language`` and sets a context-local locale."""

    def __init__(self, app: ASGIApp, *, default_locale: str = "en") -> None:
        self._app = app
        self._default_locale = default_locale

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return

        locale = self._default_locale
        headers = dict(scope.get("headers", []))
        accept_lang = headers.get(b"accept-language", b"").decode("latin-1")
        if accept_lang:
            locale = self._parse_accept_language(accept_lang)

        token = request_locale_var.set(locale)
        try:
            await self._app(scope, receive, send)
        finally:
            request_locale_var.reset(token)

    def _parse_accept_language(self, header: str) -> str:
        """Extract the highest-priority language tag (ignores quality weights for simplicity)."""
        parts = header.split(",")
        if not parts:
            return self._default_locale
        primary = parts[0].strip().split(";")[0].strip()
        if not primary:
            return self._default_locale
        lang = primary.split("-")[0]
        return lang.lower()
