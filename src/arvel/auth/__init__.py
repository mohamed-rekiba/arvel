"""arvel.auth — authentication state, Authenticatable, AuthManager, Gate (+ RBAC).

Import-light + core-installable: the ``Authenticatable`` mixin (the app's ``User``
subclasses it alongside ``Model``) and ``AuthManager`` (session state over a
``current_user`` ContextVar) carry no heavy deps. Heavy guard backends are gated by
``[jwt]``/``[oauth]``/``[2fa]``. Gate/Policy authorization lives in ``arvel.auth.gate``.
Grounded in knowledge/port/15-auth-authorization.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from arvel.auth.gate import AuthorizationError, Gate, GateResponse
from arvel.auth.permissions import HasRoles, Permission, Role

# Lives in core `support` (not here) so `http` can read it without an illegal http→auth edge.
from arvel.support import current_user


def _gate() -> Gate:
    from arvel.kernel import app, has_application

    if has_application() and app().bound("gate"):
        gate: Gate = app().make("gate")
        return gate
    return Gate()


@dataclass(frozen=True)
class EmailVerified:
    """Fired once when a user's email transitions to verified — the framework-level hook
    for welcome flows, audit trails, and provisioning."""

    user_id: Any
    email: str | None


async def _dispatch_auth_event(event: Any) -> None:
    """Best-effort dispatch through the app's event bus; a no-op without one."""
    from arvel.kernel import app, has_application

    if has_application() and app().bound("events"):
        try:
            await app().make("events").dispatch(event)
        except Exception:
            # best-effort means a broken listener can't fail the operation that fired it
            from arvel.kernel.logging import LogManager

            LogManager().channel("auth").warning("event_listener_failed", exc_info=True)


class Authenticatable:
    """Mixin for the app's user model (``class User(Authenticatable, Model)``)."""

    def get_auth_identifier(self) -> Any:
        return getattr(self, getattr(self, "__primary_key__", "id"), None)

    def get_auth_password(self) -> Any:
        return getattr(self, "password", None)

    def set_auth_password(self, hashed: str) -> None:
        """Store a (re)hashed credential — the inverse of ``get_auth_password`` (rehash-on-login).

        Override alongside ``get_auth_password`` if your model keeps the hash on a different field.
        """
        self.password = hashed

    async def can(self, ability: str, *args: Any) -> bool:
        return await _gate().allows(ability, *args, user=self)

    # --- email verification -----------------
    def has_verified_email(self) -> bool:
        """Whether the user's email is verified — the ``email_verified_at`` timestamp is set. Drives the ``verified`` route middleware."""
        # truthy, not is-not-None — a falsy-but-set value ("", 0) is NOT verified,
        # matching the `verified` route middleware
        return bool(getattr(self, "email_verified_at", None))

    async def mark_email_as_verified(self) -> bool:
        """Stamp the email verified **now** and persist. Returns
        ``False`` (a no-op) when already verified, else ``True`` — so callers can skip re-notifying."""
        if self.has_verified_email():
            return False
        from arvel.dates import now

        self.email_verified_at = now()
        await self.save()
        await _dispatch_auth_event(
            EmailVerified(user_id=self.get_auth_identifier(), email=getattr(self, "email", None))
        )
        return True

    async def mark_email_as_unverified(self) -> None:
        """Clear the verified timestamp and persist (e.g. after an email change), so the user must
        re-verify. The inverse of:meth:`mark_email_as_verified`."""
        self.email_verified_at = None
        await self.save()

    def email_for_verification(self) -> Any:
        """The address a verification link is sent to."""
        return getattr(self, "email", None)

    if (
        TYPE_CHECKING
    ):  # provided by the host Model the mixin is combined with (User(Authenticatable, Model))
        email_verified_at: Any

        async def save(self) -> Any: ...


class AuthManager:
    """Session-state guard over ``current_user`` (token/session backends are follow-ons)."""

    def __init__(self, app: Any = None, *, limiter: Any = None) -> None:
        self.app = app
        self._limiter = limiter  # optional LoginRateLimiter for failed-login lockout

    def user(self) -> Any:
        return current_user.get()

    def check(self) -> bool:
        return current_user.get() is not None

    def guest(self) -> bool:
        return not self.check()

    def id(self) -> Any:
        user = self.user()
        if user is None:
            return None
        if isinstance(user, Authenticatable):
            return user.get_auth_identifier()
        return getattr(user, "id", None)

    def login(self, user: Any) -> Any:
        """Set ``current_user`` directly — for **non-HTTP** contexts (jobs, console commands) where
        there's no request/session to persist to. This does **not** touch a session or rotate a
        session id; for a web login use ``arvel.auth.guards.SessionGuard.login(user, request)``
        instead, which does both (fixation defence + a session a later request can re-authenticate
        from)."""
        current_user.set(user)
        return user

    def logout(self) -> None:
        current_user.set(None)

    async def attempt(self, credentials: dict[str, Any], provider: Any) -> bool:
        """Resolve a user via ``provider``, verify the password through the local guard, log in.

        When a ``limiter`` is configured, a locked-out identifier fails fast; each failed attempt is
        counted and a successful login clears the counter (G3 brute-force lockout).
        """
        from arvel.auth.audit import audit

        identifier = str(credentials.get("email") or credentials.get("username") or "")
        limiter = self._limiter
        if limiter is not None and identifier and await limiter.too_many_attempts(identifier):
            audit("auth.login.blocked", level="warning", identifier=identifier, reason="locked_out")
            return False

        user = await provider(credentials)
        ok = False
        if user is not None:
            from arvel.auth.guards import LocalGuard

            async def _lookup(_identifier: str) -> Any:
                return user.get_auth_password()

            principal = await LocalGuard(_lookup).attempt(
                identifier, credentials.get("password", "")
            )
            ok = principal is not None

        if not ok:
            if limiter is not None and identifier:
                await limiter.record_failure(identifier)
            audit("auth.login.failed", level="warning", identifier=identifier)
            return False

        if limiter is not None and identifier:
            await limiter.clear(identifier)
        await self._rehash_if_needed(user, credentials.get("password", ""))
        self.login(user)
        audit("auth.login.succeeded", user_id=self.id())
        return True

    @staticmethod
    async def _rehash_if_needed(user: Any, password: str) -> None:
        """Transparently upgrade a stale password hash on a correct login (rehash-on-login, G10).

        Only acts when the stored hash actually needs upgrading and the user can persist + accept a
        new hash; otherwise a no-op — so non-persistable users (e.g. test doubles) are unaffected.
        """
        stored = user.get_auth_password()
        if not (stored and password):
            return
        if not (hasattr(user, "set_auth_password") and hasattr(user, "save")):
            return
        from arvel.security import resolve_hasher

        hasher = resolve_hasher()
        if hasher.needs_rehash(stored):  # cheap param-inspection, no offload needed
            user.set_auth_password(await hasher.make_async(password))
            await user.save()


__all__ = [
    "AuthManager",
    "Authenticatable",
    "AuthorizationError",
    "EmailVerified",
    "Gate",
    "GateResponse",
    "HasRoles",
    "Permission",
    "Role",
    "current_user",
]
