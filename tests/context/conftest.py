"""Shared fixtures for context module tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def echo_app() -> ASGIApp:
    """Minimal ASGI app that returns 200 OK with a JSON body."""

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        await receive()
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [[b"content-type", b"application/json"]],
            }
        )
        await send({"type": "http.response.body", "body": b'{"ok":true}'})

    return app


@pytest.fixture
def make_scope() -> Any:
    """Factory that creates a minimal HTTP scope dict."""

    def _make(
        *,
        path: str = "/",
        method: str = "GET",
        headers: list[tuple[bytes, bytes]] | None = None,
    ) -> dict[str, Any]:
        return {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "path": path,
            "headers": headers or [],
            "state": {},
        }

    return _make
