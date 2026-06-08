"""Tests for SetLocaleMiddleware.
Tests are written RED — the module arvel.i18n.middleware does not exist yet.
"""

from __future__ import annotations

from typing import cast

import httpx2 as httpx
import pytest
from starlette.requests import Request
from starlette.responses import Response
from starlette.testclient import TestClient
from starlette.types import ASGIApp, Receive, Scope, Send

# helpers


def _make_app(supported: list[str] | None = None, default: str = "en") -> ASGIApp:
    """Minimal ASGI app that echoes request.state.locale in the response body."""
    from arvel.i18n.middleware import SetLocaleMiddleware

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope)
        locale = getattr(request.state, "locale", "MISSING")
        response = Response(content=locale, media_type="text/plain")
        await response(scope, receive, send)

    kwargs: dict[str, object] = {}
    if supported is not None:
        kwargs["supported"] = supported
    kwargs["default"] = default

    return SetLocaleMiddleware(inner, **kwargs)  # type: ignore[arg-type]


#: importable


def test_import() -> None:
    """SetLocaleMiddleware must be importable from arvel.i18n.middleware."""
    from arvel.i18n.middleware import SetLocaleMiddleware

    assert callable(SetLocaleMiddleware)


#: Accept-Language negotiation


def test_accept_language_negotiation() -> None:
    """es wins when es is in supported and has higher q than en."""
    client = cast("httpx.Client", TestClient(_make_app(supported=["en", "es"])))
    response = client.get("/", headers={"Accept-Language": "es, en;q=0.9"})
    assert response.text == "es"


def test_accept_language_exact_match() -> None:
    client = cast("httpx.Client", TestClient(_make_app(supported=["en", "fr", "ar"])))
    response = client.get("/", headers={"Accept-Language": "fr"})
    assert response.text == "fr"


def test_accept_language_unsupported_falls_back() -> None:
    client = cast("httpx.Client", TestClient(_make_app(supported=["en"], default="en")))
    response = client.get("/", headers={"Accept-Language": "zh"})
    assert response.text == "en"


#: User locale preference wins over header


def test_user_locale_wins_over_header() -> None:
    """request.state.user.locale wins over Accept-Language header.

    The user must be stamped on scope["state"] BEFORE SetLocaleMiddleware runs.
    We model this with an outer ASGI layer that injects the user, wrapping
    the middleware which wraps the real handler.
    """
    from arvel.i18n.middleware import SetLocaleMiddleware

    class FakeUser:
        locale = "ar"

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope)
        locale = getattr(request.state, "locale", "MISSING")
        response = Response(content=locale, media_type="text/plain")
        await response(scope, receive, send)

    # Middleware wraps inner handler
    locale_middleware = SetLocaleMiddleware(inner, supported=["en", "ar"], default="en")

    # Outer ASGI layer injects the user BEFORE the middleware resolves locale
    async def outer(scope: Scope, receive: Receive, send: Send) -> None:
        scope.setdefault("state", {})
        scope["state"]["user"] = FakeUser()
        await locale_middleware(scope, receive, send)

    client = cast("httpx.Client", TestClient(outer))
    response = client.get("/", headers={"Accept-Language": "en"})
    assert response.text == "ar"


# No user → header wins


def test_no_user_header_wins() -> None:
    client = cast("httpx.Client", TestClient(_make_app(supported=["en", "es"], default="en")))
    response = client.get("/", headers={"Accept-Language": "es"})
    assert response.text == "es"


# No header, no user → default


def test_default_locale_when_no_header() -> None:
    client = cast("httpx.Client", TestClient(_make_app(supported=["en", "fr"], default="en")))
    response = client.get("/")
    assert response.text == "en"


#: Malformed Accept-Language does not raise


@pytest.mark.parametrize(
    "header",
    [
        "q=abc",
        ",,,",
        "*",
        ";;",
        "   ",
        ",en,",
    ],
)
def test_malformed_accept_language_does_not_raise(header: str) -> None:
    client = cast("httpx.Client", TestClient(_make_app(supported=["en"], default="en")))
    response = client.get("/", headers={"Accept-Language": header})
    assert response.status_code == 200
    assert response.text == "en"


# Content-Language response header (setdefault)


def test_content_language_header_set_on_response() -> None:
    client = cast("httpx.Client", TestClient(_make_app(supported=["en", "es"], default="en")))
    response = client.get("/", headers={"Accept-Language": "es"})
    assert response.headers.get("content-language") == "es"


def test_content_language_not_overwritten_if_already_set() -> None:
    """Handler-set Content-Language must not be overwritten."""
    from arvel.i18n.middleware import SetLocaleMiddleware

    async def handler(scope: Scope, receive: Receive, send: Send) -> None:
        response = Response(content="ok", headers={"Content-Language": "fr"})
        await response(scope, receive, send)

    app = SetLocaleMiddleware(handler, supported=["en", "es"], default="en")
    client = cast("httpx.Client", TestClient(app))
    response = client.get("/", headers={"Accept-Language": "es"})
    assert response.headers["content-language"] == "fr"


# Non-HTTP scope passthrough


def test_websocket_scope_passthrough() -> None:
    """Non-HTTP scopes must pass through without modification."""
    import asyncio

    from arvel.i18n.middleware import SetLocaleMiddleware

    called: list[str] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        called.append(scope["type"])

    app = SetLocaleMiddleware(inner, supported=["en"])

    async def run() -> None:
        from starlette.types import Message

        scope: Scope = {"type": "websocket", "path": "/ws", "headers": []}

        async def noop_receive() -> Message:
            return {}

        async def noop_send(_message: Message) -> None:
            pass

        await app(scope, noop_receive, noop_send)

    asyncio.run(run())
    assert called == ["websocket"]
