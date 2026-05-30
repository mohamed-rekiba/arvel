"""Tests for SecurityHeadersMiddleware — FR-032-04 / AC-08..10.

Tests are written RED — arvel.http.middleware.SecurityHeadersMiddleware does not exist yet.
"""

from __future__ import annotations

from starlette.responses import Response
from starlette.testclient import TestClient
from starlette.types import ASGIApp, Receive, Scope, Send


def _echo_app() -> ASGIApp:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        response = Response(content="ok")
        await response(scope, receive, send)

    return app


def _app_with_custom_csp(csp_value: str) -> ASGIApp:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        response = Response(content="ok", headers={"Content-Security-Policy": csp_value})
        await response(scope, receive, send)

    return app


# ─── AC-08: All 4 security headers present ────────────────────────────────────


def test_all_four_headers_present() -> None:
    from arvel.http.middleware import SecurityHeadersMiddleware

    client = TestClient(SecurityHeadersMiddleware(_echo_app()))
    response = client.get("/")

    assert response.headers.get("strict-transport-security")
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("referrer-policy")
    assert response.headers.get("content-security-policy")


def test_hsts_includes_preload() -> None:
    from arvel.http.middleware import SecurityHeadersMiddleware

    client = TestClient(SecurityHeadersMiddleware(_echo_app()))
    response = client.get("/")
    hsts = response.headers["strict-transport-security"]
    assert "preload" in hsts
    assert "includeSubDomains" in hsts


def test_csp_includes_frame_ancestors_none() -> None:
    from arvel.http.middleware import SecurityHeadersMiddleware

    client = TestClient(SecurityHeadersMiddleware(_echo_app()))
    response = client.get("/")
    csp = response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp


# ─── AC-09: setdefault semantics — no overwrite ────────────────────────────────


def test_csp_not_overwritten_when_handler_sets_it() -> None:
    from arvel.http.middleware import SecurityHeadersMiddleware

    custom_csp = "default-src 'none'"
    client = TestClient(SecurityHeadersMiddleware(_app_with_custom_csp(custom_csp)))
    response = client.get("/")
    assert response.headers["content-security-policy"] == custom_csp


# ─── AC-09b: Custom csp constructor param used ────────────────────────────────


def test_custom_csp_via_constructor() -> None:
    from arvel.http.middleware import SecurityHeadersMiddleware

    custom_csp = "default-src 'none'; script-src 'none'"
    client = TestClient(SecurityHeadersMiddleware(_echo_app(), csp=custom_csp))
    response = client.get("/")
    assert response.headers["content-security-policy"] == custom_csp


def test_custom_hsts_max_age() -> None:
    from arvel.http.middleware import SecurityHeadersMiddleware

    client = TestClient(SecurityHeadersMiddleware(_echo_app(), hsts_max_age=86400))
    response = client.get("/")
    hsts = response.headers["strict-transport-security"]
    assert "max-age=86400" in hsts


# ─── AC-10: WebSocket scope is no-op ─────────────────────────────────────────


def test_websocket_scope_passthrough() -> None:
    import asyncio

    from arvel.http.middleware import SecurityHeadersMiddleware

    called: list[str] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        called.append(scope["type"])

    app = SecurityHeadersMiddleware(inner)

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


# ─── import path ─────────────────────────────────────────────────────────────


def test_importable_from_http_middleware() -> None:
    from arvel.http.middleware import SecurityHeadersMiddleware
    from arvel.http.middleware.security_headers import (
        SecurityHeadersMiddleware as SecurityHeadersMiddlewareAlias,
    )

    assert SecurityHeadersMiddleware is SecurityHeadersMiddlewareAlias
