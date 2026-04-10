"""Tests for VerifiedMiddleware — blocks unverified users."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from arvel.auth.middleware_verified import VerifiedMiddleware

if TYPE_CHECKING:
    from starlette.requests import Request


async def protected_endpoint(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def _app_verified() -> Starlette:
    app = Starlette(routes=[Route("/dashboard", protected_endpoint)])
    app.add_middleware(VerifiedMiddleware, testing=True)
    return app


class TestVerifiedMiddleware:
    def test_verified_user_passes(self) -> None:
        """FR-011: Verified users can access protected routes."""
        client = TestClient(_app_verified())
        response = client.get(
            "/dashboard",
            headers={"X-Test-Verified": "true"},
        )
        assert response.status_code == 200

    def test_unverified_user_gets_403(self) -> None:
        """FR-011: Unverified users get 403."""
        client = TestClient(_app_verified())
        response = client.get(
            "/dashboard",
            headers={"X-Test-Verified": "false"},
        )
        assert response.status_code == 403
        assert "verify" in response.json()["error"]["message"].lower()

    def test_no_auth_state_gets_403(self) -> None:
        """No auth state at all returns 403."""
        client = TestClient(_app_verified())
        response = client.get("/dashboard")
        assert response.status_code == 403

    def test_non_http_scope_passes_through(self) -> None:
        """Non-HTTP scopes (websocket, lifespan) pass through."""
        app = _app_verified()
        client = TestClient(app)
        response = client.get("/dashboard", headers={"X-Test-Verified": "true"})
        assert response.status_code == 200
