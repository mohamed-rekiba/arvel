"""arvel.auth.password_reset — parity **stored** password-reset broker (A6 fix).

Replaces the old stateless signed-token approach (a signed token was replayable within its TTL —
audit finding A6): ``PasswordResetToken`` holds **one row per email** — only the token's ``Hasher``
hash is stored, never the plaintext — and ``PasswordBroker`` is the send/verify surface. A used *or*
expired token is **deleted**, so a replay always fails, even inside the original TTL window. Sends are
throttled per email (one every ``throttle_seconds``). Grounded in
projects/arvel/specs/14-auth-session.md.
"""

from __future__ import annotations

import inspect
import secrets
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar

from arvel.database import Model

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

DEFAULT_THROTTLE_SECONDS = 60  # one send per email per minute
DEFAULT_TTL_SECONDS = 3600  # 1 hour


class PasswordResetStatus(Enum):
    """The outcome of a ``send_reset_link``/``reset`` call — an Enum, never a bare string."""

    RESET_SUCCESS = "reset_success"
    INVALID_TOKEN = "invalid_token"  # noqa: S105 (enum status label)  # nosec B105
    INVALID_USER = "invalid_user"
    RESET_THROTTLED = "reset_throttled"
    EXPIRED = "expired"


@dataclass(frozen=True)
class PasswordResetRequested:
    """Fired on a successful ``send_reset_link``. ``token`` is the **plaintext** — the app's listener
    needs it to build the mailed link (only the hash is ever persisted) — so never log this event."""

    email: str
    token: str


@dataclass(frozen=True)
class PasswordReset:
    """Fired after a successful ``reset``."""

    email: str


class PasswordResetToken(Model):
    """One active reset token per email (``email`` is the primary key — a fresh ``send_reset_link``
    replaces an unthrottled row rather than ever holding two live tokens for the same address); only
    ``token_hash`` (a ``Hasher`` hash) is stored, never the plaintext token."""

    __table_name__ = "password_reset_tokens"
    __primary_key__ = "email"
    __timestamps__ = False  # only `created_at` — it alone drives both throttle + TTL
    __fields__: ClassVar[dict[str, Any]] = {"email": str, "token_hash": str, "created_at": str}
    __fillable__: ClassVar[list[str]] = ["email", "token_hash", "created_at"]
    __casts__: ClassVar[dict[str, str]] = {"created_at": "datetime"}


def _age_seconds(created_at: Any) -> float:
    from arvel.dates import Date

    return float((Date.now().to_py() - created_at.to_py()).total_seconds())


class PasswordBroker:
    """``PasswordBroker`` parity: throttled ``send_reset_link`` + single-use ``reset``.

    ``user_lookup(email)`` resolves the user for an email (the broker owns no user store — bring your
    own, e.g. ``User.where(email=email).first()``). ``dispatcher`` defaults to the container's bound
    ``events`` service when an application is booted, else dispatch is a best-effort no-op (mirrors
    ``arvel.auth.audit``: a missing dispatcher must never break the reset flow).
    """

    def __init__(
        self,
        user_lookup: Callable[[str], Awaitable[Any | None]],
        *,
        throttle_seconds: int = DEFAULT_THROTTLE_SECONDS,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        dispatcher: Any = None,
        hasher: Any = None,
    ) -> None:
        self._user_lookup = user_lookup
        self._throttle = throttle_seconds
        self._ttl = ttl_seconds
        self._dispatcher = dispatcher
        self._hasher = hasher

    def _hash(self) -> Any:
        if self._hasher is None:
            from arvel.security import resolve_hasher

            self._hasher = resolve_hasher()
        return self._hasher

    async def _dispatch(self, event: Any) -> None:
        dispatcher = self._dispatcher
        if dispatcher is None:
            from arvel.kernel import app, has_application

            if has_application() and app().bound("events"):
                dispatcher = app().make("events")
        if dispatcher is not None:
            await dispatcher.dispatch(event)

    async def send_reset_link(self, email: str) -> PasswordResetStatus:
        """Throttle (one per ``throttle_seconds`` per email), store a freshly hashed token, and fire
        ``PasswordResetRequested`` — the app's listener sends the actual email."""
        user = await self._user_lookup(email)
        if user is None:
            return PasswordResetStatus.INVALID_USER

        existing = await PasswordResetToken.where(email=email).first()
        if existing is not None:
            if _age_seconds(existing.created_at) < self._throttle:
                return PasswordResetStatus.RESET_THROTTLED
            await existing.delete()  # past the throttle window — replaced below

        from arvel.dates import Date

        token = secrets.token_urlsafe(32)
        await PasswordResetToken.create(
            email=email, token_hash=self._hash().make(token), created_at=Date.now()
        )
        await self._dispatch(PasswordResetRequested(email=email, token=token))
        return PasswordResetStatus.RESET_SUCCESS

    async def reset(
        self,
        email: str,
        token: str,
        new_password: str,
        callback: Callable[[Any, str], Any],
    ) -> PasswordResetStatus:
        """Verify the stored hash + TTL; on success set the password via ``callback(user,
        new_password)``, delete the token row (single-use — a replay always fails, even inside the
        TTL), rotate the user's remember token, and fire ``PasswordReset``."""
        user = await self._user_lookup(email)
        if user is None:
            return PasswordResetStatus.INVALID_USER

        record = await PasswordResetToken.where(email=email).first()
        if record is None:
            return PasswordResetStatus.INVALID_TOKEN

        if _age_seconds(record.created_at) > self._ttl:
            await record.delete()  # expired — clean up so it can never be replayed later
            return PasswordResetStatus.EXPIRED

        if not self._hash().check(token, record.token_hash):
            return PasswordResetStatus.INVALID_TOKEN

        await record.delete()  # single-use: consumed now, regardless of what the callback does

        outcome = callback(user, new_password)
        if inspect.isawaitable(outcome):
            await outcome

        from arvel.auth.remember import clear_all_remember_tokens

        identifier = user.get_auth_identifier() if hasattr(user, "get_auth_identifier") else user.id
        await clear_all_remember_tokens(int(identifier))

        await self._dispatch(PasswordReset(email=email))
        return PasswordResetStatus.RESET_SUCCESS


__all__ = [
    "DEFAULT_THROTTLE_SECONDS",
    "DEFAULT_TTL_SECONDS",
    "PasswordBroker",
    "PasswordReset",
    "PasswordResetRequested",
    "PasswordResetStatus",
    "PasswordResetToken",
]
