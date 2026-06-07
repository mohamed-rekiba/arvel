"""``AuthService`` — register / login / refresh / logout / me.

Uses the framework's ``User`` and ``RefreshToken`` models directly.
No ``UserProvider`` indirection — same approach as Laravel's ``AuthManager``.
"""

from __future__ import annotations

import importlib
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy.exc import IntegrityError

from arvel.auth.config import JwtConfig
from arvel.auth.events import (
    LoggedIn,
    LoggedOut,
    LoginFailed,
    Registered,
    TokenReuseDetected,
)
from arvel.auth.exceptions import (
    AccountSuspendedError,
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    TokenReuseDetectedError,
)
from arvel.auth.models import RefreshToken
from arvel.auth.refresh_tokens import (
    generate_refresh_token,
    hash_refresh_token,
    refresh_token_expires_at,
)
from arvel.auth.token_pair import TokenPair
from arvel.database.db import DB
from arvel.facades.event import Event as EventFacade
from arvel.facades.hash import Hash
from arvel.logging.facade import Log

_DEFAULT_ACCESS_TTL = timedelta(minutes=15)
_DEFAULT_REFRESH_TTL = timedelta(days=14)
_DEFAULT_JWT_ALGORITHM = "HS256"


def _default_user_model() -> type[Any]:
    """Lazy-import the framework's default ``User`` model."""
    from arvel.auth.models.user import User  # noqa: PLC0415

    return User


def _coerce_pk(user_id_str: str) -> int | str:
    """Convert a user-ID string to int when it's purely numeric.

    The JWT ``sub`` claim is always a string, but apps that use integer PKs
    pass that string straight to ``Model.find()``, which hands it to asyncpg.
    asyncpg rejects a ``str`` for an ``INT`` column, so we coerce here rather
    than requiring every app to handle the conversion itself.
    """
    try:
        return int(user_id_str)
    except ValueError:
        return user_id_str


class AuthService:
    """Stateless orchestrator for the password-grant authentication flow."""

    def __init__(
        self,
        *,
        jwt: JwtConfig,
        refresh_ttl: timedelta = _DEFAULT_REFRESH_TTL,
        user_model: type[Any] | None = None,
    ) -> None:
        if not jwt.secret:
            msg = "AuthService jwt_secret is required"
            raise ValueError(msg)
        self._jwt_secret = jwt.secret
        self._jwt_algorithm = jwt.algorithm
        self._jwt_issuer = jwt.issuer or None
        self._jwt_audience = jwt.audience or None
        self._access_ttl = timedelta(seconds=jwt.ttl_seconds)
        self._refresh_ttl = refresh_ttl
        self._user_cls: type[Any] = user_model if user_model is not None else _default_user_model()

    # ─── Register ──────────────────────────────────────────────────────────

    async def register(
        self,
        *,
        name: str,
        email: str,
        password: str,
        locale: str | None = None,
    ) -> Any:
        """Create a user with an argon2id-hashed password.

        Raises:
            EmailAlreadyRegisteredError: a row with this email already exists.
        """
        user_cls = self._user_cls
        password_hash = Hash.make(password)
        normalised = email.strip().lower()
        Log.debug("auth.registering")
        async with DB.transaction():
            try:
                user = await user_cls.create(
                    name=name,
                    email=normalised,
                    password=password_hash,
                    locale=locale,
                )
            except IntegrityError as exc:
                Log.debug("auth.register.rejected", reason="email_taken")
                msg = f"email {email!r} is already registered"
                raise EmailAlreadyRegisteredError(msg) from exc
        await EventFacade.dispatch(
            Registered(user_id=str(user.id), email=normalised, occurred_at=_now())
        )
        Log.debug("auth.registered", user_id=str(user.id))
        return user

    # ─── Login ─────────────────────────────────────────────────────────────

    async def login(self, *, email: str, password: str) -> tuple[Any, TokenPair]:
        """Validate credentials and issue an access + refresh pair.

        Returns:
            (user, TokenPair) on success.

        Raises:
            InvalidCredentialsError: unknown email or wrong password.
            EmailNotVerifiedError: ``email_verified_at`` is NULL.
            AccountSuspendedError: ``suspended_at`` is non-NULL.
        """
        user_cls = self._user_cls
        normalised = email.strip().lower()
        Log.debug("auth.login.attempt")
        user = await user_cls.where(email=normalised).first()

        if user is None or not Hash.check(password, str(getattr(user, "password", ""))):
            await self._dispatch_login_failed(normalised)
            Log.debug("auth.login.failed", reason="invalid_credentials")
            msg = "invalid credentials"
            raise InvalidCredentialsError(msg)

        if getattr(user, "suspended_at", None) is not None:
            await self._dispatch_login_failed(normalised, user_id=str(user.id))
            Log.debug("auth.login.failed", user_id=str(user.id), reason="suspended")
            msg = "account suspended"
            raise AccountSuspendedError(msg)

        if getattr(user, "email_verified_at", None) is None:
            await self._dispatch_login_failed(normalised, user_id=str(user.id))
            Log.debug("auth.login.failed", user_id=str(user.id), reason="email_unverified")
            msg = "email not verified"
            raise EmailNotVerifiedError(msg)

        tokens = await self._issue_pair(user_id=str(user.id))
        await EventFacade.dispatch(
            LoggedIn(user_id=str(user.id), email=normalised, occurred_at=_now())
        )
        Log.debug("auth.login.succeeded", user_id=str(user.id))
        return user, tokens

    async def issue_for(self, *, user_id: str, email: str = "") -> TokenPair:
        """Mint a token pair for an already-authenticated user.

        Skips credential checks — the caller (e.g. social login) has already
        proven identity through another channel.
        """
        tokens = await self._issue_pair(user_id=user_id)
        await EventFacade.dispatch(LoggedIn(user_id=user_id, email=email, occurred_at=_now()))
        return tokens

    # ─── Refresh ───────────────────────────────────────────────────────────

    async def refresh(self, *, refresh_token: str) -> tuple[Any, TokenPair]:
        """Rotate a refresh token and mint a new access JWT.

        Rotation revokes the presented row rather than deleting it, so replaying
        an already-rotated token is detectable theft: the whole token family is
        revoked and TokenReuseDetectedError is raised.

        Raises:
            InvalidCredentialsError: token unknown / expired / user gone.
            TokenReuseDetectedError: a previously rotated token was replayed.
        """
        user_cls = self._user_cls
        digest = hash_refresh_token(refresh_token)
        Log.debug("auth.refreshing")

        async with DB.transaction():
            row = await RefreshToken.where(token_hash=digest).first()
            if row is None:
                Log.debug("auth.refresh.rejected", reason="unknown_token")
                msg = "refresh token unknown"
                raise InvalidCredentialsError(msg)
            replayed = row.revoked_at is not None
            expired = row.is_expired
            user_id_str = row.user_id
            if not replayed and not expired:
                row.revoked_at = _now()
                await row.save()

        if replayed:
            Log.debug("auth.refresh.rejected", reason="token_reuse")
            await self.revoke_family(user_id=user_id_str)  # raises when rows remain
            msg = "refresh token reuse detected"
            raise InvalidCredentialsError(msg)

        if expired:
            async with DB.transaction():
                await RefreshToken.where(token_hash=digest).delete()
            Log.debug("auth.refresh.rejected", reason="expired_token")
            msg = "refresh token expired"
            raise InvalidCredentialsError(msg)

        user = await user_cls.find(_coerce_pk(user_id_str))
        if user is None:
            Log.debug("auth.refresh.rejected", reason="user_gone")
            msg = "user no longer exists"
            raise InvalidCredentialsError(msg)

        tokens = await self._issue_pair(user_id=user_id_str)
        Log.debug("auth.refreshed", user_id=user_id_str)
        return user, tokens

    async def revoke_family(self, *, user_id: str) -> int:
        """Delete every refresh-token row for ``user_id`` and dispatch
        :class:`TokenReuseDetected`. Raises :class:`TokenReuseDetectedError`
        when any rows were deleted.
        """
        user_cls = self._user_cls
        async with DB.transaction():
            count = await RefreshToken.where(user_id=user_id).delete()
        if count:
            user = await user_cls.find(_coerce_pk(user_id))
            email = str(getattr(user, "email", ""))
            await EventFacade.dispatch(
                TokenReuseDetected(user_id=user_id, email=email, occurred_at=_now())
            )
            msg = "refresh-token reuse detected; all sessions revoked"
            raise TokenReuseDetectedError(msg)
        return count

    # ─── Logout ────────────────────────────────────────────────────────────

    async def logout(self, *, refresh_token: str | None) -> None:
        """Delete the supplied refresh row. Idempotent — missing/unknown is fine."""
        user_cls = self._user_cls
        if not refresh_token:
            return
        digest = hash_refresh_token(refresh_token)
        async with DB.transaction():
            row = await RefreshToken.where(token_hash=digest).first()
            if row is None:
                return
            user_id_str = row.user_id
            await row.delete()

        user = await user_cls.find(_coerce_pk(user_id_str))
        email = str(getattr(user, "email", ""))
        await EventFacade.dispatch(LoggedOut(user_id=user_id_str, email=email, occurred_at=_now()))
        Log.debug("auth.logged_out", user_id=user_id_str)

    # ─── Me ────────────────────────────────────────────────────────────────

    async def me(self, *, access_token: str) -> Any:
        """Decode an access JWT and return the owning user.

        Raises:
            InvalidCredentialsError: missing / expired / malformed token.
            AccountSuspendedError: account became suspended after token issuance.
        """
        user_cls = self._user_cls
        try:
            claims = self._decode_access(access_token)
        except _JwtDecodeError as exc:
            msg = "invalid access token"
            raise InvalidCredentialsError(msg) from exc

        sub = claims.get("sub")
        if not isinstance(sub, str):
            msg = "JWT missing sub claim"
            raise InvalidCredentialsError(msg)

        user = await user_cls.find(_coerce_pk(sub))
        if user is None:
            msg = "user no longer exists"
            raise InvalidCredentialsError(msg)
        if getattr(user, "suspended_at", None) is not None:
            msg = "account suspended"
            raise AccountSuspendedError(msg)
        return user

    # ─── helpers ───────────────────────────────────────────────────────────

    async def _issue_pair(self, *, user_id: str) -> TokenPair:
        access_jwt = self.issue_access_token(subject=user_id)
        plain_refresh = generate_refresh_token()
        digest = hash_refresh_token(plain_refresh)
        csrf = secrets.token_urlsafe(32)
        async with DB.transaction():
            await RefreshToken.create(
                user_id=user_id,
                token_hash=digest,
                expires_at=refresh_token_expires_at(self._refresh_ttl),
            )
        return TokenPair(
            access_token=access_jwt,
            refresh_token=plain_refresh,
            csrf_token=csrf,
            expires_in=int(self._access_ttl.total_seconds()),
        )

    def issue_access_token(self, *, subject: str) -> str:
        """Mint an access JWT for a user id."""

        jwt_mod = importlib.import_module("jwt")
        now = int(time.time())
        payload: dict[str, object] = {
            "sub": subject,
            "exp": now + int(self._access_ttl.total_seconds()),
            "jti": secrets.token_hex(16),
            "typ": "access",
        }
        if self._jwt_issuer is not None:
            payload["iss"] = self._jwt_issuer
        if self._jwt_audience is not None:
            payload["aud"] = self._jwt_audience
        encoded = jwt_mod.encode(payload, self._jwt_secret, algorithm=self._jwt_algorithm)
        return str(encoded)

    def _decode_access(self, token: str) -> dict[str, object]:
        jwt_mod = importlib.import_module("jwt")
        try:
            raw = jwt_mod.decode(
                token,
                self._jwt_secret,
                algorithms=[self._jwt_algorithm],
                issuer=self._jwt_issuer,
                audience=self._jwt_audience,
                options={"require": ["exp", "sub"]},
            )
        except Exception as exc:
            msg = f"jwt decode failed: {type(exc).__name__}"
            raise _JwtDecodeError(msg) from exc
        if not isinstance(raw, dict):
            msg = "jwt payload was not a dict"
            raise _JwtDecodeError(msg)
        claims: dict[str, object] = {}
        for raw_key, value in cast("dict[object, object]", raw).items():
            claims[str(raw_key)] = value
        if claims.get("typ") != "access":
            msg = f"unexpected token typ {claims.get('typ')!r}"
            raise _JwtDecodeError(msg)
        return claims

    async def _dispatch_login_failed(
        self,
        email: str,
        *,
        user_id: str | None = None,
    ) -> None:
        await EventFacade.dispatch(LoginFailed(user_id=user_id, email=email, occurred_at=_now()))


class _JwtDecodeError(Exception):
    """Internal — raised by ``_decode_access`` on any pyjwt failure."""


def _now() -> datetime:
    return datetime.now(tz=UTC)


# ─── Application-scoped accessor ───────────────────────────────────────────
# Mirrors the Auth facade pattern. AuthServiceProvider calls set_current()
# at registration time so route helpers can call get_auth_service() without
# needing a DI container reference.

_current: AuthService | None = None


def set_current(service: AuthService) -> None:
    """Bind the application-scoped ``AuthService`` instance (called by ``AuthServiceProvider``)."""
    global _current  # noqa: PLW0603
    _current = service


def get_auth_service() -> AuthService:
    """Return the application-scoped ``AuthService`` bound by ``AuthServiceProvider``."""
    if _current is None:
        msg = "AuthService is not bound. Did AuthServiceProvider run?"
        raise RuntimeError(msg)
    return _current


__all__ = ["AuthService", "get_auth_service"]
