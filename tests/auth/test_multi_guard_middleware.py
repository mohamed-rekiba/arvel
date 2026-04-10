"""Tests for multi-guard middleware — parameterized auth middleware integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from arvel.auth.auth_manager import AuthManager
from arvel.auth.guard import AuthGuardMiddleware
from arvel.auth.guards.api_key_guard import ApiKeyGuard
from arvel.auth.guards.jwt_guard import JwtGuard
from arvel.auth.tokens import TokenService

if TYPE_CHECKING:
    from starlette.requests import Request


def _token_service() -> TokenService:
    return TokenService(secret_key="test-secret-key-that-is-long-enough")


def _auth_manager() -> AuthManager:
    return AuthManager(
        guards={
            "jwt": JwtGuard(token_service=_token_service()),
            "api_key": ApiKeyGuard(api_keys=["test-api-key-123"]),
        },
        default="jwt",
    )


async def protected_endpoint(request: Request) -> JSONResponse:
    state = request.scope.get("state", {})
    return JSONResponse(
        {
            "user_id": state.get("auth_user_id"),
            "guard": state.get("auth_guard"),
        }
    )


def _app_with_jwt_guard() -> Starlette:
    app = Starlette(routes=[Route("/api", protected_endpoint)])
    app.add_middleware(
        AuthGuardMiddleware,
        auth_manager=_auth_manager(),
        guard_name="jwt",
    )
    return app


def _app_with_api_key_guard() -> Starlette:
    app = Starlette(routes=[Route("/service", protected_endpoint)])
    app.add_middleware(
        AuthGuardMiddleware,
        auth_manager=_auth_manager(),
        guard_name="api_key",
    )
    return app


def _app_with_default_guard() -> Starlette:
    app = Starlette(routes=[Route("/default", protected_endpoint)])
    app.add_middleware(
        AuthGuardMiddleware,
        auth_manager=_auth_manager(),
    )
    return app


class TestMultiGuardMiddleware:
    def test_jwt_guard_authenticates_bearer_token(self) -> None:
        """FR-002: JWT guard validates Bearer tokens."""
        svc = _token_service()
        token = svc.create_access_token("user-42")
        client = TestClient(_app_with_jwt_guard())

        response = client.get("/api", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        assert response.json()["user_id"] == "user-42"
        assert response.json()["guard"] == "jwt"

    def test_api_key_guard_authenticates_api_key(self) -> None:
        """FR-003: API key guard validates X-API-Key header."""
        client = TestClient(_app_with_api_key_guard())

        response = client.get("/service", headers={"X-API-Key": "test-api-key-123"})

        assert response.status_code == 200
        assert response.json()["guard"] == "api_key"

    def test_default_guard_used_when_no_guard_name(self) -> None:
        """FR-005b: Default guard when no parameter given."""
        svc = _token_service()
        token = svc.create_access_token("user-99")
        client = TestClient(_app_with_default_guard())

        response = client.get("/default", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        assert response.json()["user_id"] == "user-99"

    def test_jwt_guard_rejects_invalid_token(self) -> None:
        client = TestClient(_app_with_jwt_guard())

        response = client.get("/api", headers={"Authorization": "Bearer bad.token"})

        assert response.status_code == 401

    def test_api_key_guard_rejects_wrong_key(self) -> None:
        client = TestClient(_app_with_api_key_guard())

        response = client.get("/service", headers={"X-API-Key": "wrong-key"})

        assert response.status_code == 401

    def test_jwt_guard_rejects_api_key(self) -> None:
        """NFR-002: No cross-guard token reuse."""
        client = TestClient(_app_with_jwt_guard())

        response = client.get("/api", headers={"X-API-Key": "test-api-key-123"})

        assert response.status_code == 401

    def test_api_key_guard_rejects_bearer_token(self) -> None:
        """NFR-002: No cross-guard token reuse."""
        svc = _token_service()
        token = svc.create_access_token("user-42")
        client = TestClient(_app_with_api_key_guard())

        response = client.get("/service", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 401

    def test_missing_credentials_returns_401(self) -> None:
        client = TestClient(_app_with_jwt_guard())

        response = client.get("/api")

        assert response.status_code == 401

    def test_auth_context_includes_guard_name(self) -> None:
        """FR-006: AuthContext.guard field."""
        svc = _token_service()
        token = svc.create_access_token("user-42")
        client = TestClient(_app_with_jwt_guard())

        response = client.get("/api", headers={"Authorization": f"Bearer {token}"})

        assert response.json()["guard"] == "jwt"
