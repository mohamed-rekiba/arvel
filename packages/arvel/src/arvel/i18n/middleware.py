"""SetLocaleMiddleware — per-request locale negotiation.

Resolution order on every HTTP request:

1. ``request.state.user.locale`` — authenticated user's stored preference wins,
 so a user who set Spanish in profile settings keeps Spanish even when their
 browser sends ``Accept-Language: en``.
2. ``Accept-Language`` header, RFC 9110 §12.5.4 quality-value sorted. We pick
 the highest-q tag whose primary subtag matches a supported locale.
3. ``default`` locale (constructor arg, default ``"en"``).

The negotiated locale is stamped on ``request.state.locale`` and mirrored to
the response via ``Content-Language`` (setdefault — never overwrites a
handler-set value). The shared ``Translator`` is *never* mutated, so
concurrent requests are safe; callers pass ``locale`` to
``Translator.get(..., locale=...)`` or use the :func:`arvel.i18n.t` helper.

Pure ASGI — avoids Starlette's ``BaseHTTPMiddleware`` which buffers streaming
responses and can cause Content-Length mismatches.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_DEFAULT_LOCALE: str = "en"


class SetLocaleMiddleware:
    """Negotiate the request locale and stamp it on request state and response."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        supported: Sequence[str] = ("en",),
        default: str = _DEFAULT_LOCALE,
    ) -> None:
        self._app = app
        self._supported = tuple(supported)
        self._default = default

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        locale = self._resolve(scope)

        # Starlette keeps scope["state"] as a plain dict; Request.state wraps
        # it lazily. Write through the dict so attribute access works downstream.
        scope.setdefault("state", {})
        scope["state"]["locale"] = locale

        async def send_with_locale(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("Content-Language", locale)
            await send(message)

        await self._app(scope, receive, send_with_locale)

    def _resolve(self, scope: Scope) -> str:
        user_locale = self._user_locale(scope)
        if user_locale is not None:
            return user_locale

        headers_list: list[tuple[bytes, bytes]] = scope.get("headers", [])
        for name, value in headers_list:
            if name.lower() == b"accept-language":
                negotiated = self._negotiate_header(value.decode("latin-1"))
                if negotiated is not None:
                    return negotiated

        return self._default

    def _user_locale(self, scope: Scope) -> str | None:
        state: dict[str, object] | None = scope.get("state")
        if not isinstance(state, dict):
            return None
        user = state.get("user")
        if user is None:
            return None
        candidate = getattr(user, "locale", None)
        if isinstance(candidate, str) and candidate in self._supported:
            return candidate
        return None

    def _negotiate_header(self, header: str) -> str | None:
        for tag in _parse_accept_language(header):
            primary = tag.partition("-")[0].lower()
            if primary in self._supported:
                return primary
        return None


def _parse_accept_language(header: str) -> Iterable[str]:
    """Yield Accept-Language tags in descending quality order (RFC 9110 §12.5.4)."""
    entries: list[tuple[float, int, str]] = []
    for index, raw in enumerate(header.split(",")):
        cleaned = raw.strip()
        if not cleaned:
            continue
        tag, _, params = cleaned.partition(";")
        tag = tag.strip()
        if not tag:
            continue
        quality = _parse_quality(params)
        entries.append((quality, index, tag))
    entries.sort(key=lambda item: (-item[0], item[1]))
    return [tag for _q, _idx, tag in entries]


def _parse_quality(params: str) -> float:
    for part in params.split(";"):
        key, _, value = part.partition("=")
        if key.strip().lower() == "q":
            try:
                return max(0.0, min(1.0, float(value.strip())))
            except ValueError:
                return 0.0
    return 1.0


__all__ = ["SetLocaleMiddleware"]
