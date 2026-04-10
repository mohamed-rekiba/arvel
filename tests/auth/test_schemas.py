"""Tests for auth request/response schemas — validation and defaults."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from arvel.auth.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    VerifyEmailRequest,
)


class TestRegisterRequest:
    def test_valid_registration(self) -> None:
        req = RegisterRequest(email="user@example.com", password="securepass1")
        assert req.email == "user@example.com"
        assert req.password == "securepass1"

    def test_invalid_email_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(email="not-an-email", password="securepass1")

    def test_short_password_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(email="user@example.com", password="short")

    def test_long_password_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(email="user@example.com", password="x" * 73)


class TestLoginRequest:
    def test_valid_login(self) -> None:
        req = LoginRequest(email="user@example.com", password="mypassword")
        assert req.email == "user@example.com"

    def test_invalid_email_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LoginRequest(email="bad", password="mypassword")


class TestRefreshRequest:
    def test_valid_refresh(self) -> None:
        req = RefreshRequest(refresh_token="abc.def.ghi")
        assert req.refresh_token == "abc.def.ghi"


class TestTokenResponse:
    def test_defaults(self) -> None:
        resp = TokenResponse(access_token="at", refresh_token="rt")
        assert resp.token_type == "bearer"

    def test_serialization(self) -> None:
        resp = TokenResponse(access_token="at", refresh_token="rt")
        data = resp.model_dump()
        assert data["access_token"] == "at"
        assert data["refresh_token"] == "rt"
        assert data["token_type"] == "bearer"


class TestForgotPasswordRequest:
    def test_valid_email(self) -> None:
        req = ForgotPasswordRequest(email="user@example.com")
        assert req.email == "user@example.com"

    def test_invalid_email_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ForgotPasswordRequest(email="not-valid")


class TestResetPasswordRequest:
    def test_valid_request(self) -> None:
        req = ResetPasswordRequest(token="abc123", password="newpass12")
        assert req.token == "abc123"

    def test_short_password_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ResetPasswordRequest(token="abc123", password="short")


class TestVerifyEmailRequest:
    def test_valid_request(self) -> None:
        req = VerifyEmailRequest(token="verify-token")
        assert req.token == "verify-token"


class TestMessageResponse:
    def test_message(self) -> None:
        resp = MessageResponse(message="Success")
        assert resp.message == "Success"
