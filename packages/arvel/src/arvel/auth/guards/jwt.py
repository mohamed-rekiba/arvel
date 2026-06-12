"""``JwtGuard`` — validates a Bearer JWT and resolves the user.

The guard's only responsibilities are:

- Pull the ``Authorization: Bearer …`` header off the request.
- Verify the token (signature, ``exp``, optional ``aud``, alg-confusion guard).
- Reject refresh-typed tokens used as access tokens.
- Resolve the ``sub`` claim through the configured ``UserResolver``.

Issuance and rotation moved to :class:`arvel.auth.AuthBroker` —
the guard is no longer a token mint.

Security:

- Refuses ``alg=none`` outright (alg-confusion defence).
- Enforces minimum 32-byte HMAC secret.
- Always verifies signature and expiry.
"""

from __future__ import annotations

import importlib
import secrets
import time
from datetime import timedelta
from typing import Any, Protocol, cast

from arvel.auth.config import JwtConfig
from arvel.auth.guard import Guard, UserResolver
from arvel.auth.mixins import Authenticatable

_MIN_HMAC_SECRET_BYTES = 32
_HMAC_ALGS = frozenset({"HS256", "HS384", "HS512"})
_JWT_ACCESS_CLAIM = "access"


def _as_int(value: object) -> int | None:
    """Coerce a JWT numeric claim (``iat``) to int, or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


class _JwtDecode(Protocol):
    """Minimal interface for jwt.decode so pyright can reason about the return type."""

    def __call__(  # noqa: PLR0913
        self,
        jwt: str,
        key: str,
        *,
        algorithms: list[str],
        audience: str | None = ...,
        issuer: str | None = ...,
        leeway: int = ...,
        options: dict[str, Any] | None = ...,
    ) -> dict[str, Any]: ...


class JwtGuard(Guard):
    def __init__(
        self,
        *,
        resolver: UserResolver,
        jwt: JwtConfig,
        leeway_seconds: int = 0,
    ) -> None:
        if jwt.algorithm.lower() == "none":
            msg = "JwtGuard refuses algorithm 'none' — sign your tokens."
            raise ValueError(msg)
        if jwt.algorithm in _HMAC_ALGS and len(jwt.secret.encode("utf-8")) < _MIN_HMAC_SECRET_BYTES:
            msg = (
                f"JwtGuard HMAC secret must be at least {_MIN_HMAC_SECRET_BYTES} bytes "
                f"(got {len(jwt.secret.encode('utf-8'))})."
            )
            raise ValueError(msg)

        self._resolver = resolver
        self._secret_or_key = jwt.secret
        self._algorithm = jwt.algorithm
        self._audience = jwt.audience or None
        self._issuer = jwt.issuer or None
        self._leeway = leeway_seconds

    @property
    def secret_or_key(self) -> str:
        return self._secret_or_key

    @property
    def algorithm(self) -> str:
        return self._algorithm

    @property
    def audience(self) -> str | None:
        return self._audience

    @property
    def issuer(self) -> str | None:
        return self._issuer

    async def user(self, request: Any) -> Any | None:
        token = self._extract_bearer(request)
        if token is None:
            return None

        try:
            _jwt_mod = importlib.import_module("jwt")
        except ImportError as exc:
            raise ImportError(
                "JwtGuard requires arvel[jwt]. Install with: pip install 'arvel[jwt]'"
            ) from exc

        # getattr returns Any — avoids Unknown member access on unresolved module
        _decode: _JwtDecode = cast("_JwtDecode", _jwt_mod.decode)
        _exc_mod = _jwt_mod.exceptions
        _invalid_token_error: type[Exception] = _exc_mod.InvalidTokenError

        try:
            payload = _decode(
                token,
                self._secret_or_key,
                algorithms=[self._algorithm],
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": ["exp"]},
            )
        except _invalid_token_error:
            return None

        # Reject tokens with a wrong or absent typ claim. Refresh tokens carry
        # typ="refresh" and must not be usable as access credentials — matching
        # AuthService._decode_access() which also requires typ=="access".
        if payload.get("typ") != _JWT_ACCESS_CLAIM:
            return None

        sub = payload.get("sub")
        if not isinstance(sub, str):
            return None

        from arvel.auth.token_denylist import is_revoked  # noqa: PLC0415

        if await is_revoked(
            jti=str(payload.get("jti", "")),
            subject=sub,
            issued_at=_as_int(payload.get("iat")),
        ):
            return None
        user = await self._resolver.by_id(sub)
        return None if isinstance(user, Authenticatable) and user.is_suspended else user

    async def issue_token(
        self,
        *,
        subject: str,
        expires_in: timedelta,
        claims: dict[str, object] | None = None,
    ) -> str:
        """Mint a short-lived access JWT (``typ=access``).

        Used by the upcoming ``AuthBroker`` to mint the access leg of the
        access+refresh token pair. Refresh tokens are opaque (not JWTs) and
        live in the ``refresh_tokens`` table via :class:`RefreshToken`.
        """
        extra = dict(claims or {})
        extra["typ"] = _JWT_ACCESS_CLAIM
        return self._encode(subject=subject, expires_in=expires_in, extra_claims=extra)

    def _encode(
        self,
        *,
        subject: str,
        expires_in: timedelta,
        extra_claims: dict[str, object],
    ) -> str:
        _jwt_mod = importlib.import_module("jwt")
        now = int(time.time())
        payload: dict[str, object] = {
            "sub": subject,
            "iat": now,
            "exp": now + int(expires_in.total_seconds()),
            "jti": secrets.token_hex(16),
            **extra_claims,
        }
        if self._audience is not None:
            payload["aud"] = self._audience
        if self._issuer is not None:
            payload["iss"] = self._issuer
        encoded = _jwt_mod.encode(payload, self._secret_or_key, algorithm=self._algorithm)
        return str(encoded)

    @staticmethod
    def _extract_bearer(request: Any) -> str | None:
        headers = getattr(request, "headers", {})
        try:
            items = dict(headers)
        except TypeError, ValueError:
            return None
        lower = {str(k).lower(): str(v) for k, v in items.items()}
        raw = lower.get("authorization", "")
        if not raw.lower().startswith("bearer "):
            return None
        return raw[7:].strip() or None
