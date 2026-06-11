"""``EmailVerificationService`` — signed URL verification.

Stateless apart from the signing secret. Uses the ``User`` model directly
to mark ``email_verified_at``.  Stateless verification: no DB writes on the
issue side; the HMAC-SHA256-signed payload encodes ``{id, h}`` where ``h``
is the first 16 hex chars of ``sha256(user.email)``.  The hash invariant
means a stale link cannot verify a changed email address.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, cast

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from arvel.auth.events import EmailVerified
from arvel.auth.exceptions import EmailVerificationInvalidError
from arvel.facades.event import Event as EventFacade

_SALT = "arvel.auth.email_verification"


def _default_user_model() -> type[Any]:
    """Lazy-import the framework's default ``User`` model."""
    from arvel.auth.models.user import User  # noqa: PLC0415

    return User


class EmailVerificationService:
    """Mint and consume signed email-verification URLs."""

    def __init__(
        self,
        *,
        secret: str,
        ttl_seconds: int = 60 * 60,
        user_model: type[Any] | None = None,
    ) -> None:
        if not secret:
            msg = "EmailVerificationService secret is required"
            raise ValueError(msg)
        self._serializer: URLSafeTimedSerializer = URLSafeTimedSerializer(secret, salt=_SALT)
        self._ttl_seconds = ttl_seconds
        self._user_cls: type[Any] = user_model if user_model is not None else _default_user_model()

    def issue(self, *, user_id: str, email: str) -> str:
        """Mint a signed payload encoding ``{user_id, email_hash}``."""
        payload = {"id": user_id, "h": _email_hash(email)}
        return self._serializer.dumps(payload)

    async def issue_for_email(self, email: str) -> str | None:
        """Mint a token for an unverified user by email, or None if there's nothing to do.

        Returns None when no matching user exists or they're already verified.
        Callers must respond uniformly regardless, so a missing account is
        indistinguishable from a verified one.
        """
        normalised = email.strip().lower()
        user = await self._user_cls.where(email=normalised).first()
        if user is None or user.is_verified:
            return None
        return self.issue(user_id=str(user.id), email=str(getattr(user, "email", normalised)))

    def build_url(self, *, base_url: str, signed: str) -> str:
        """Compose ``{base_url}/{signed}`` with no trailing slash on the base."""
        return f"{base_url.rstrip('/')}/{signed}"

    def peek(self, signed: str) -> tuple[str, str]:
        """Verify the signature and decode ``(user_id, email_hash)`` — no side effect.

        Raises:
            EmailVerificationInvalidError: signature mismatch or TTL elapsed.
        """
        try:
            data = self._serializer.loads(signed, max_age=self._ttl_seconds)
        except SignatureExpired as exc:
            msg = "verification link expired"
            raise EmailVerificationInvalidError(msg) from exc
        except BadSignature as exc:
            msg = "verification link is invalid"
            raise EmailVerificationInvalidError(msg) from exc

        if not isinstance(data, dict):
            msg = "verification payload is malformed"
            raise EmailVerificationInvalidError(msg)
        payload = cast("dict[str, object]", data)
        try:
            user_id = str(payload["id"])
            email_hash = str(payload["h"])
        except (KeyError, TypeError) as exc:
            msg = "verification payload is malformed"
            raise EmailVerificationInvalidError(msg) from exc

        return user_id, email_hash

    async def consume(self, signed: str) -> Any:
        """Validate a signed URL, mark the user verified, dispatch ``EmailVerified``.

        Raises:
            EmailVerificationInvalidError: signature/TTL/user/email mismatch.
        """
        user_id, email_hash = self.peek(signed)

        user = await self._user_cls.find(_coerce_pk(user_id))
        if user is None:
            msg = "verification target no longer exists"
            raise EmailVerificationInvalidError(msg)

        email = str(getattr(user, "email", ""))
        if _email_hash(email) != email_hash:
            msg = "verification link no longer matches user's email"
            raise EmailVerificationInvalidError(msg)

        user.email_verified_at = datetime.now(tz=UTC)
        await user.save()

        await EventFacade.dispatch(
            EmailVerified(user_id=user_id, email=email, occurred_at=datetime.now(tz=UTC))
        )
        return user


def _coerce_pk(value: str) -> int | str:
    """Cast a numeric PK string to int so integer-PK models match on find()."""
    return int(value) if value.isdigit() else value


def _email_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:16]


__all__ = ["EmailVerificationService"]
