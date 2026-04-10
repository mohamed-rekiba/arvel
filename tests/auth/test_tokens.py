"""Tests for JWT token service."""

from __future__ import annotations

import time
from typing import Any

import pytest

from arvel.auth.tokens import TokenService
from arvel.security.exceptions import AuthenticationError


class TestTokenService:
    def _service(self, **kwargs: Any) -> TokenService:
        return TokenService(secret_key="test-secret-key-that-is-long-enough", **kwargs)

    def test_create_access_token(self) -> None:
        svc = self._service()
        token = svc.create_access_token("user-123")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_access_token(self) -> None:
        svc = self._service()
        token = svc.create_access_token("user-123")
        payload = svc.decode_token(token, expected_type="access")
        assert payload["sub"] == "user-123"
        assert payload["type"] == "access"

    def test_decode_refresh_token(self) -> None:
        svc = self._service()
        token = svc.create_refresh_token("user-123")
        payload = svc.decode_token(token, expected_type="refresh")
        assert payload["sub"] == "user-123"
        assert payload["type"] == "refresh"

    def test_create_token_pair(self) -> None:
        svc = self._service()
        pair = svc.create_token_pair("user-123")
        assert "access_token" in pair
        assert "refresh_token" in pair
        assert pair["token_type"] == "bearer"

    def test_expired_token_raises(self) -> None:
        svc = self._service(access_ttl_minutes=0)
        token = svc.create_access_token("user-123")
        time.sleep(1)
        with pytest.raises(AuthenticationError, match="expired"):
            svc.decode_token(token)

    def test_wrong_type_raises(self) -> None:
        svc = self._service()
        token = svc.create_refresh_token("user-123")
        with pytest.raises(AuthenticationError, match="Expected access"):
            svc.decode_token(token, expected_type="access")

    def test_invalid_token_raises(self) -> None:
        svc = self._service()
        with pytest.raises(AuthenticationError, match="Invalid token"):
            svc.decode_token("not.a.token")

    def test_extra_claims(self) -> None:
        svc = self._service()
        token = svc.create_access_token("user-123", extra_claims={"role": "admin"})
        payload = svc.decode_token(token)
        assert payload["role"] == "admin"

    def test_empty_secret_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            TokenService(secret_key="")

    def test_custom_issuer_audience(self) -> None:
        svc = self._service(issuer="myapp", audience="myapi")
        token = svc.create_access_token("user-123")
        payload = svc.decode_token(token)
        assert payload["iss"] == "myapp"
        assert payload["aud"] == "myapi"
