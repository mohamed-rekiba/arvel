"""Tests for password reset and email verification token service."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from arvel.auth.password_reset import ResetTokenService
from arvel.security.exceptions import AuthenticationError

SECRET = "test-reset-secret-key"


class TestResetTokenCreation:
    def test_create_reset_token(self) -> None:
        svc = ResetTokenService(SECRET)
        token = svc.create_reset_token("user-123")
        assert token.startswith("reset:user-123:")
        parts = token.split(":")
        assert len(parts) == 4

    def test_create_verification_token(self) -> None:
        svc = ResetTokenService(SECRET)
        token = svc.create_verification_token("user-456")
        assert token.startswith("verify:user-456:")
        parts = token.split(":")
        assert len(parts) == 4

    def test_tokens_are_unique(self) -> None:
        svc = ResetTokenService(SECRET)
        tokens = {svc.create_reset_token("user-1") for _ in range(5)}
        assert len(tokens) >= 1  # same second yields same timestamp


class TestResetTokenValidation:
    def test_valid_reset_token(self) -> None:
        svc = ResetTokenService(SECRET)
        token = svc.create_reset_token("user-123")
        assert svc.validate_reset_token(token, "user-123") is True

    def test_valid_verification_token(self) -> None:
        svc = ResetTokenService(SECRET)
        token = svc.create_verification_token("user-456")
        assert svc.validate_verification_token(token, "user-456") is True

    def test_wrong_user_id_raises(self) -> None:
        svc = ResetTokenService(SECRET)
        token = svc.create_reset_token("user-123")
        with pytest.raises(AuthenticationError, match="user mismatch"):
            svc.validate_reset_token(token, "user-999")

    def test_wrong_purpose_raises(self) -> None:
        svc = ResetTokenService(SECRET)
        token = svc.create_reset_token("user-123")
        with pytest.raises(AuthenticationError, match="Expected verify"):
            svc.validate_verification_token(token, "user-123")

    def test_tampered_signature_raises(self) -> None:
        svc = ResetTokenService(SECRET)
        token = svc.create_reset_token("user-123")
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
        with pytest.raises(AuthenticationError, match="Invalid token signature"):
            svc.validate_reset_token(tampered, "user-123")

    def test_malformed_token_raises(self) -> None:
        svc = ResetTokenService(SECRET)
        with pytest.raises(AuthenticationError, match="Malformed"):
            svc.validate_reset_token("bad-token", "user-123")

    def test_expired_reset_token_raises(self) -> None:
        svc = ResetTokenService(SECRET, reset_ttl_minutes=1)
        token = svc.create_reset_token("user-123")
        future_time = time.time() + 120
        with patch("arvel.auth.password_reset.time") as mock_time:
            mock_time.time.return_value = future_time
            with pytest.raises(AuthenticationError, match="expired"):
                svc.validate_reset_token(token, "user-123")

    def test_single_use_enforcement(self) -> None:
        svc = ResetTokenService(SECRET)
        token = svc.create_reset_token("user-123")
        assert svc.validate_reset_token(token, "user-123") is True
        with pytest.raises(AuthenticationError, match="already been used"):
            svc.validate_reset_token(token, "user-123")

    def test_empty_secret_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            ResetTokenService("")
