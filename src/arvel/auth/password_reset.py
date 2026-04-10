"""Password reset and email verification token service.

Generates single-use, time-limited tokens for password reset and email
verification flows. Tokens are HMAC-signed so they can be validated
without server-side storage (stateless), though a used-token set is
maintained in-memory for single-use enforcement.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from arvel.security.exceptions import AuthenticationError


class ResetTokenService:
    """Generates and validates password-reset and email-verification tokens.

    Tokens are ``{purpose}:{user_id}:{timestamp_hex}:{signature}`` where the
    signature is HMAC-SHA256 over the first three parts. Single-use is enforced
    via an in-memory set of consumed token fingerprints.
    """

    def __init__(
        self,
        secret_key: str,
        *,
        reset_ttl_minutes: int = 60,
        verify_ttl_hours: int = 24,
    ) -> None:
        if not secret_key:
            raise ValueError("Reset token secret key must not be empty")
        self._secret = secret_key.encode()
        self._reset_ttl = reset_ttl_minutes * 60
        self._verify_ttl = verify_ttl_hours * 3600
        self._consumed: set[str] = set()

    def create_reset_token(self, user_id: str) -> str:
        """Create a time-limited, single-use password reset token."""
        return self._create("reset", user_id, self._reset_ttl)

    def create_verification_token(self, user_id: str) -> str:
        """Create a time-limited email verification token."""
        return self._create("verify", user_id, self._verify_ttl)

    def validate_reset_token(self, token: str, expected_user_id: str) -> bool:
        """Validate a password reset token. Consumes it on success."""
        return self._validate(token, "reset", expected_user_id, self._reset_ttl)

    def validate_verification_token(self, token: str, expected_user_id: str) -> bool:
        """Validate an email verification token. Consumes it on success."""
        return self._validate(token, "verify", expected_user_id, self._verify_ttl)

    def _create(self, purpose: str, user_id: str, _ttl: int) -> str:
        timestamp = format(int(time.time()), "x")
        data = f"{purpose}:{user_id}:{timestamp}"
        sig = hmac.new(self._secret, data.encode(), hashlib.sha256).hexdigest()
        return f"{data}:{sig}"

    def _validate(self, token: str, expected_purpose: str, expected_user_id: str, ttl: int) -> bool:
        parts = token.split(":")
        if len(parts) != 4:
            raise AuthenticationError("Malformed token", code="TOKEN_MALFORMED")

        purpose, user_id, timestamp_hex, provided_sig = parts

        data = f"{purpose}:{user_id}:{timestamp_hex}"
        expected_sig = hmac.new(self._secret, data.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(provided_sig, expected_sig):
            raise AuthenticationError("Invalid token signature", code="TOKEN_INVALID")

        if purpose != expected_purpose:
            raise AuthenticationError(
                f"Expected {expected_purpose} token, got {purpose}",
                code="TOKEN_TYPE_MISMATCH",
            )

        if user_id != expected_user_id:
            raise AuthenticationError("Token user mismatch", code="TOKEN_USER_MISMATCH")

        try:
            created_at = int(timestamp_hex, 16)
        except ValueError as e:
            raise AuthenticationError("Malformed token timestamp", code="TOKEN_MALFORMED") from e

        elapsed = int(time.time()) - created_at
        if elapsed > ttl or elapsed < 0:
            raise AuthenticationError("Token has expired", code="TOKEN_EXPIRED")

        fingerprint = hashlib.sha256(token.encode()).hexdigest()
        if fingerprint in self._consumed:
            raise AuthenticationError("Token has already been used", code="TOKEN_ALREADY_USED")
        self._consumed.add(fingerprint)

        return True
