"""CSRF double-submit middleware (RED state).

Ships ASGI-native (not BaseHTTPMiddleware) so framework exception handlers
see CsrfMismatchException correctly.
"""

from __future__ import annotations

import pytest
from arvel.auth.middleware.csrf_double_submit import (
    CsrfDoubleSubmitMiddleware,
    CsrfMismatchException,
)
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

# test ASGI app


async def _ok_handler(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


def _make_app(exempt_paths: list[str] | None = None) -> Starlette:
    app = Starlette(
        routes=[
            Route("/api/auth/refresh", _ok_handler, methods=["POST"]),
            Route("/api/auth/login", _ok_handler, methods=["POST"]),
        ]
    )
    app.add_middleware(
        CsrfDoubleSubmitMiddleware,  # type: ignore[arg-type]
        exempt_paths=exempt_paths,
    )
    return app


@pytest.mark.asyncio
async def test_matching_cookie_and_header_passes() -> None:
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set("_csrf", "my-csrf-token")
        response = await client.post(
            "/api/auth/refresh",
            headers={"X-CSRF-TOKEN": "my-csrf-token"},
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_missing_header_returns_403() -> None:
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set("_csrf", "my-csrf-token")
        response = await client.post("/api/auth/refresh")
    assert response.status_code == 403
    data = response.json()
    assert data["error"]["code"] == "CSRF_MISMATCH"


@pytest.mark.asyncio
async def test_mismatched_header_returns_403() -> None:
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set("_csrf", "token-A")
        response = await client.post(
            "/api/auth/refresh",
            headers={"X-CSRF-TOKEN": "token-B"},
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_exempt_paths_skip_check() -> None:
    """Login, register, forgot-password, reset-password, verify-email are exempt."""
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Login has no _csrf cookie but should not be blocked.
        response = await client.post("/api/auth/login")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_problemdetailshandler_sees_exception() -> None:
    """Closes — CsrfMismatchException is a concrete exception class."""
    exc = CsrfMismatchException("CSRF token mismatch.")
    assert exc.status_code == 403
    assert exc.code == "CSRF_MISMATCH"
    assert "CSRF_MISMATCH" in exc.to_dict()["error"]["code"]
