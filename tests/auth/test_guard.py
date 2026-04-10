"""Tests for the AuthGuardMiddleware."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from arvel.auth.auth_manager import AuthManager
from arvel.auth.guard import AuthGuardMiddleware
from arvel.auth.guards.jwt_guard import JwtGuard
from arvel.auth.tokens import TokenService

if TYPE_CHECKING:
    from starlette.requests import Request


def _token_service() -> TokenService:
    return TokenService(secret_key="test-secret-key-that-is-long-enough")


async def protected_endpoint(request: Request) -> JSONResponse:
    user_id = request.scope.get("state", {}).get("auth_user_id")
    return JSONResponse({"user_id": user_id})


async def public_endpoint(request: Request) -> JSONResponse:
    return JSONResponse({"message": "public"})


def _app() -> Starlette:
    app = Starlette(
        routes=[
            Route("/protected", protected_endpoint),
            Route("/login", public_endpoint),
        ],
    )
    auth_manager = AuthManager(
        guards={"jwt": JwtGuard(token_service=_token_service())},
        default="jwt",
    )
    app.add_middleware(
        AuthGuardMiddleware,
        auth_manager=auth_manager,
        exclude_paths={"/login"},
    )
    return app


class TestAuthGuardMiddleware:
    def test_excluded_path_passes(self) -> None:
        client = TestClient(_app())
        response = client.get("/login")
        assert response.status_code == 200
        assert response.json()["message"] == "public"

    def test_missing_header_returns_401(self) -> None:
        client = TestClient(_app())
        response = client.get("/protected")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTH_REQUIRED"

    def test_invalid_token_returns_401(self) -> None:
        client = TestClient(_app())
        response = client.get("/protected", headers={"Authorization": "Bearer invalid.token.here"})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTH_REQUIRED"

    def test_valid_token_passes(self) -> None:
        svc = _token_service()
        token = svc.create_access_token("user-42")
        client = TestClient(_app())
        response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["user_id"] == "user-42"

    def test_no_bearer_prefix_returns_401(self) -> None:
        svc = _token_service()
        token = svc.create_access_token("user-42")
        client = TestClient(_app())
        response = client.get("/protected", headers={"Authorization": f"Token {token}"})
        assert response.status_code == 401
