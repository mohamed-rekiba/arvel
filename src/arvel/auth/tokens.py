"""JWT token service — issue, validate, and refresh access/refresh tokens."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from arvel.security.exceptions import AuthenticationError


class TokenService:
    """Issues and validates JWT access and refresh tokens."""

    def __init__(
        self,
        secret_key: str,
        *,
        algorithm: str = "HS256",
        access_ttl_minutes: int = 60,
        refresh_ttl_days: int = 30,
        issuer: str = "arvel",
        audience: str = "arvel-app",
    ) -> None:
        if not secret_key:
            raise ValueError("JWT secret key must not be empty")
        self._secret = secret_key
        self._algorithm = algorithm
        self._access_ttl = timedelta(minutes=access_ttl_minutes)
        self._refresh_ttl = timedelta(days=refresh_ttl_days)
        self._issuer = issuer
        self._audience = audience

    def create_access_token(self, subject: str, extra_claims: dict[str, Any] | None = None) -> str:
        """Create a short-lived access token."""
        return self._encode(
            subject=subject,
            token_type="access",  # noqa: S106
            ttl=self._access_ttl,
            extra_claims=extra_claims,
        )

    def create_refresh_token(self, subject: str) -> str:
        """Create a long-lived refresh token."""
        return self._encode(
            subject=subject,
            token_type="refresh",  # noqa: S106
            ttl=self._refresh_ttl,
        )

    def create_token_pair(
        self, subject: str, extra_claims: dict[str, Any] | None = None
    ) -> dict[str, str]:
        """Create both access and refresh tokens."""
        return {
            "access_token": self.create_access_token(subject, extra_claims),
            "refresh_token": self.create_refresh_token(subject),
            "token_type": "bearer",
        }

    def decode_token(self, token: str, *, expected_type: str = "access") -> dict[str, Any]:
        """Decode and validate a JWT token.

        Raises AuthenticationError on invalid/expired tokens.
        """
        try:
            import jwt
        except ImportError as e:
            raise AuthenticationError("PyJWT is not installed: pip install PyJWT") from e

        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["exp", "iss", "aud", "sub", "type"]},
            )
        except jwt.ExpiredSignatureError as e:
            raise AuthenticationError("Token has expired", code="TOKEN_EXPIRED") from e
        except jwt.InvalidTokenError as e:
            raise AuthenticationError(f"Invalid token: {e}", code="TOKEN_INVALID") from e

        if payload.get("type") != expected_type:
            raise AuthenticationError(
                f"Expected {expected_type} token, got {payload.get('type')}",
                code="TOKEN_TYPE_MISMATCH",
            )

        return payload

    def _encode(
        self,
        *,
        subject: str,
        token_type: str,
        ttl: timedelta,
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        try:
            import jwt
        except ImportError as e:
            raise AuthenticationError("PyJWT is not installed: pip install PyJWT") from e

        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "sub": subject,
            "type": token_type,
            "iss": self._issuer,
            "aud": self._audience,
            "iat": now,
            "exp": now + ttl,
        }
        if extra_claims:
            payload.update(extra_claims)

        return jwt.encode(payload, self._secret, algorithm=self._algorithm)
