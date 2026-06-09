"""``PasswordService`` — forgot/reset password flow.

Uses ``User``, ``PasswordReset``, and ``RefreshToken`` models directly.
Dispatches ``PasswordResetRequested`` and ``PasswordResetCompleted`` events
internally — the controller never sees the plaintext reset token.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from arvel.auth.events import PasswordResetCompleted, PasswordResetRequested
from arvel.auth.exceptions import PasswordResetTokenInvalidError
from arvel.auth.models import RefreshToken
from arvel.auth.token_denylist import revoke_all_for_user
from arvel.database.db import DB
from arvel.facades.event import Event as EventFacade
from arvel.facades.hash import Hash

_DEFAULT_RESET_TTL = timedelta(minutes=60)
_DEFAULT_THROTTLE = timedelta(seconds=60)
_DEFAULT_ACCESS_TTL = timedelta(minutes=15)


def _default_user_model() -> type[Any]:
    """Lazy-import the framework's default ``User`` model."""
    from arvel.auth.models.user import User  # noqa: PLC0415

    return User


def _password_reset_model() -> type[Any]:
    """Lazy-import PasswordReset to avoid MetaData conflicts with apps that define their own."""
    from arvel.auth.models.password_reset import PasswordReset  # noqa: PLC0415

    return PasswordReset


class PasswordService:
    """Stateless orchestrator for the forgot/reset password flow."""

    def __init__(
        self,
        *,
        ttl: timedelta = _DEFAULT_RESET_TTL,
        throttle: timedelta = _DEFAULT_THROTTLE,
        user_model: type[Any] | None = None,
        access_ttl: timedelta = _DEFAULT_ACCESS_TTL,
    ) -> None:
        self._ttl = ttl
        self._throttle = throttle
        self._user_cls: type[Any] = user_model if user_model is not None else _default_user_model()
        self._access_ttl = access_ttl

    async def forgot(self, email: str) -> None:
        """Mint a reset token for a known email and dispatch ``PasswordResetRequested``.

        Returns silently for unknown emails or requests within the throttle
        window so the controller always emits a uniform 202 — no account
        enumeration signal leaks.
        """
        PasswordReset = _password_reset_model()  # noqa: N806
        normalised = email.strip().lower()

        async with DB.transaction():
            user = await self._user_cls.where(email=normalised).first()
            if user is None:
                return

            existing = await PasswordReset.where(email=normalised).first()
            if existing is not None and not _older_than(existing.created_at, self._throttle):
                return

            plain = secrets.token_urlsafe(32)
            digest = _hash_reset_token(plain)

            if existing is not None:
                await existing.delete()
            await PasswordReset.create(email=normalised, token_hash=digest)

            await EventFacade.dispatch(
                PasswordResetRequested(
                    user_id=str(user.id),
                    email=normalised,
                    reset_token=plain,
                    occurred_at=datetime.now(tz=UTC),
                )
            )

    async def reset(self, *, token: str, password: str) -> None:
        """Verify the token, update the user's password, revoke refresh family.

        The email is derived from the reset token row — no need for the caller
        to re-submit it. Dispatches ``PasswordResetCompleted`` on success.

        Raises:
            PasswordResetTokenInvalidError: token unknown / expired / user gone.
        """
        PasswordReset = _password_reset_model()  # noqa: N806
        digest = _hash_reset_token(token)
        new_hash = Hash.make(password)

        # Phase 1 — read-only validation.
        row = await PasswordReset.where(token_hash=digest).first()
        if row is None:
            msg = "reset token unknown"
            raise PasswordResetTokenInvalidError(msg)

        normalised_email = row.email

        # Phase 2 — expired-row cleanup. Commit the DELETE before raising
        # so retries with the same plaintext stop matching.
        if row.is_expired(self._ttl):
            async with DB.transaction():
                await PasswordReset.where(token_hash=digest).delete()
            msg = "reset token expired"
            raise PasswordResetTokenInvalidError(msg)

        user = await self._user_cls.where(email=normalised_email).first()
        if user is None:
            async with DB.transaction():
                await PasswordReset.where(token_hash=digest).delete()
            msg = "user no longer exists"
            raise PasswordResetTokenInvalidError(msg)

        # Phase 3 — success: password update + row burn + family revoke.
        async with DB.transaction():
            user.password = new_hash
            await user.save()
            await PasswordReset.where(token_hash=digest).delete()
            await RefreshToken.where(user_id=str(user.id)).delete()

        # Kill outstanding access tokens too — a reset must end every session,
        # not just block new refreshes.
        await revoke_all_for_user(str(user.id), ttl_seconds=int(self._access_ttl.total_seconds()))

        await EventFacade.dispatch(
            PasswordResetCompleted(
                user_id=str(user.id),
                email=normalised_email,
                occurred_at=datetime.now(tz=UTC),
            )
        )


def _hash_reset_token(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def _older_than(timestamp: datetime, window: timedelta) -> bool:
    aware = timestamp if timestamp.tzinfo is not None else timestamp.replace(tzinfo=UTC)
    return datetime.now(tz=UTC) - aware > window


__all__ = ["PasswordService"]
