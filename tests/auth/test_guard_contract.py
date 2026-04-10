"""Tests for GuardContract, JwtGuard, and ApiKeyGuard implementations."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.auth.contracts import GuardContract
from arvel.auth.guards.api_key_guard import ApiKeyGuard
from arvel.auth.guards.jwt_guard import JwtGuard
from arvel.auth.policy import AuthContext
from arvel.auth.tokens import TokenService


def _token_service() -> TokenService:
    return TokenService(secret_key="test-secret-key-that-is-long-enough")


def _make_scope(*, headers: dict[bytes, bytes] | None = None) -> dict[str, Any]:
    raw_headers = list((headers or {}).items())
    return {
        "type": "http",
        "path": "/test",
        "headers": raw_headers,
        "state": {},
    }


class TestGuardContract:
    def test_guard_contract_is_abstract(self) -> None:
        with pytest.raises(TypeError, match="abstract"):
            GuardContract()  # type: ignore[abstract]


class TestJwtGuard:
    async def test_authenticate_with_valid_token_returns_auth_context(self) -> None:
        svc = _token_service()
        guard = JwtGuard(token_service=svc)
        token = svc.create_access_token("user-42", extra_claims={"roles": ["admin"]})
        scope = _make_scope(headers={b"authorization": f"Bearer {token}".encode()})

        result = await guard.authenticate(scope)

        assert result is not None
        assert isinstance(result, AuthContext)
        assert result.sub == "user-42"
        assert result.guard == "jwt"

    async def test_authenticate_with_missing_header_returns_none(self) -> None:
        guard = JwtGuard(token_service=_token_service())
        scope = _make_scope()

        result = await guard.authenticate(scope)

        assert result is None

    async def test_authenticate_with_invalid_token_returns_none(self) -> None:
        guard = JwtGuard(token_service=_token_service())
        scope = _make_scope(headers={b"authorization": b"Bearer invalid.token.here"})

        result = await guard.authenticate(scope)

        assert result is None

    async def test_authenticate_with_non_bearer_prefix_returns_none(self) -> None:
        svc = _token_service()
        guard = JwtGuard(token_service=svc)
        token = svc.create_access_token("user-42")
        scope = _make_scope(headers={b"authorization": f"Token {token}".encode()})

        result = await guard.authenticate(scope)

        assert result is None

    def test_error_response_returns_401(self) -> None:
        guard = JwtGuard(token_service=_token_service())
        response = guard.error_response()

        assert response.status_code == 401

    async def test_authenticate_extracts_claims(self) -> None:
        svc = _token_service()
        guard = JwtGuard(token_service=svc, claims_mapper=None)
        token = svc.create_access_token("user-42")
        scope = _make_scope(headers={b"authorization": f"Bearer {token}".encode()})

        result = await guard.authenticate(scope)

        assert result is not None
        assert result.claims.get("sub") == "user-42"


class TestApiKeyGuard:
    async def test_authenticate_with_valid_key_returns_auth_context(self) -> None:
        guard = ApiKeyGuard(api_keys=["key-abc-123", "key-def-456"])
        scope = _make_scope(headers={b"x-api-key": b"key-abc-123"})

        result = await guard.authenticate(scope)

        assert result is not None
        assert isinstance(result, AuthContext)
        assert result.guard == "api_key"

    async def test_authenticate_with_invalid_key_returns_none(self) -> None:
        guard = ApiKeyGuard(api_keys=["key-abc-123"])
        scope = _make_scope(headers={b"x-api-key": b"wrong-key"})

        result = await guard.authenticate(scope)

        assert result is None

    async def test_authenticate_with_missing_header_returns_none(self) -> None:
        guard = ApiKeyGuard(api_keys=["key-abc-123"])
        scope = _make_scope()

        result = await guard.authenticate(scope)

        assert result is None

    def test_error_response_returns_401(self) -> None:
        guard = ApiKeyGuard(api_keys=["key-abc-123"])
        response = guard.error_response()

        assert response.status_code == 401

    async def test_authenticate_with_empty_key_list_returns_none(self) -> None:
        guard = ApiKeyGuard(api_keys=[])
        scope = _make_scope(headers={b"x-api-key": b"any-key"})

        result = await guard.authenticate(scope)

        assert result is None

    async def test_different_guard_tokens_not_interchangeable(self) -> None:
        """FR-007 / NFR-002: Cross-guard token isolation."""
        svc = _token_service()
        jwt_token = svc.create_access_token("user-42")

        api_guard = ApiKeyGuard(api_keys=["key-abc-123"])
        scope = _make_scope(headers={b"x-api-key": jwt_token.encode()})

        result = await api_guard.authenticate(scope)
        assert result is None
