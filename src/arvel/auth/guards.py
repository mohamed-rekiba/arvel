"""arvel.auth.guards — the authentication layer: the ``GuardDriver`` contract + ``GuardManager``.

A guard verifies a request by some method and produces a method-agnostic ``Principal``
(``arvel.auth.identity``). The ``GuardManager`` is a driver manager (the cache/storage pattern):
config selects the default guard; drivers register via ``create_<name>_driver`` or ``extend()``.
The ``local`` driver checks a password against the stored local-credential hash; the ``session``
guard reflects the established ``current_user``. Heavy/federated drivers (``jwt``, ``oidc``) are
follow-ons and stay lazily imported behind their extras.

This module is import-light on purpose: only the ``Manager`` base is imported at module load.
``identity`` (which pulls ``arvel.database``), the ``Hasher``, and ``AuthIdentity`` are imported
lazily inside methods so importing guards never drags the heavy core in (NFR G2). Grounded in
DR-0009 and projects/arvel/architecture/auth-rearchitecture.md.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

from arvel.support.manager import Manager

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from arvel.auth.identity import Principal


@runtime_checkable
class GuardDriver(Protocol):
    """A driver that verifies a request and returns a ``Principal`` (or ``None``)."""

    async def verify(self, request: Any) -> Principal | None: ...


class LocalGuard:
    """Password guard: check a credential against the stored local hash → ``Principal('local', id)``.

    ``lookup`` is an async callable ``(identifier) -> hashed_credential | None``. The default
    ``GuardManager`` wires it to the ``local`` ``AuthIdentity.credential``; tests inject a fake.
    """

    def __init__(
        self,
        lookup: Callable[[str], Awaitable[str | None]],
        hasher: Any = None,
    ) -> None:
        self._lookup = lookup
        self._hasher = hasher

    def _hash(self) -> Any:
        if self._hasher is None:
            from arvel.security import resolve_hasher

            self._hasher = resolve_hasher()
        return self._hasher

    async def attempt(self, identifier: str, password: str) -> Principal | None:
        hashed = await self._lookup(identifier)
        if not hashed:
            return None
        if not self._hash().check(password, hashed):
            return None
        from arvel.auth.identity import Principal

        return Principal(provider="local", subject=identifier)

    async def verify(self, request: Any) -> Principal | None:
        form = await request.form()
        identifier = form.get("email") or form.get("username")
        password = form.get("password")
        if not identifier or not password:
            return None
        return await self.attempt(str(identifier), str(password))


class SessionGuard:
    """Reflects the established session — a ``Principal`` for the ``current_user``, else ``None``.

    :meth:`login`/:meth:`logout` are the request-aware, session-persisting counterpart to
    ``AuthManager.login``/``logout`` (which only ever touch the ``current_user`` ContextVar — no
    session, no fixation defence, no remember-me). :meth:`user_id` is the read-half: feed it to your
    ``user_resolver`` binding (mirrors ``TokenGuard.user_id`` for the bearer-token path) so a later
    request re-authenticates from the session instead of the (per-request) ContextVar.
    """

    #: the session key ``login``/``user_id`` read+write — shared with ``arvel.auth.remember``,
    #: ``arvel.auth.impersonation``, and ``arvel.auth.sessions.EnsureSessionCurrent``.
    SESSION_KEY = "_user_id"

    async def login(self, user: Any, request: Any, *, remember: bool = False) -> None:
        """Log ``user`` in for this request: rotate the session id **before** persisting the user id
        (fixation defence — a pre-login, possibly attacker-fixed, id is never reused for an
        authenticated session), persist it to ``request.session`` so a later request re-authenticates
        without the user re-submitting credentials, and set ``current_user`` for the rest of this
        request. When ``remember``, also issue a rotating remember-me cookie
        (:func:`arvel.auth.remember.remember`)."""
        from arvel.http.session import regenerate_session

        regenerate_session(request)  # BEFORE writing the session user id (fixation defence)
        session = getattr(request, "session", None)
        if isinstance(session, dict):
            from arvel.auth import Authenticatable

            subject = (
                user.get_auth_identifier()
                if isinstance(user, Authenticatable)
                else getattr(user, "id", None)
            )
            cast("dict[str, Any]", session)[self.SESSION_KEY] = subject

        from arvel.auth import current_user

        current_user.set(user)
        if remember:
            from arvel.auth.remember import remember as issue_remember_cookie

            await issue_remember_cookie(request, user)

    async def logout(self, request: Any) -> None:
        """Log out for this request: clear the remember cookie/token, invalidate the session (new id,
        all data — including the persisted user id — dropped), and clear ``current_user``."""
        from arvel.auth.remember import forget_remember
        from arvel.http.session import invalidate_session

        await forget_remember(request)  # delete the token row + flag the cookie cleared
        invalidate_session(request)  # new id; drops SESSION_KEY and everything else

        from arvel.auth import current_user

        current_user.set(None)

    async def user_id(self, request: Any) -> Any:
        """The session-persisted user id (the read-half of :meth:`login`), else ``None`` when there's
        no session or nobody's logged in over it."""
        session = getattr(request, "session", None)
        if not isinstance(session, dict):
            return None
        return cast("dict[str, Any]", session).get(self.SESSION_KEY)

    async def verify(self, request: Any = None) -> Principal | None:
        from arvel.auth import Authenticatable, current_user

        user = current_user.get()
        if user is None:
            return None
        subject = (
            user.get_auth_identifier()
            if isinstance(user, Authenticatable)
            else getattr(user, "id", None)
        )
        from arvel.auth.identity import Principal

        return Principal(provider="session", subject=str(subject))


async def _db_credential_lookup(identifier: str) -> str | None:
    """Default local-credential lookup: the hash stored on the ``local`` ``AuthIdentity``."""
    from arvel.auth.identity import AuthIdentity

    record = await AuthIdentity.where(provider="local", subject=identifier).first()
    return str(record.credential) if record is not None else None


class GuardManager(Manager):
    """Resolves authentication guards by config; ``guard()`` aliases ``driver()``."""

    def default_driver(self) -> str:
        if self.app is not None and hasattr(self.app, "config"):
            return str(self.app.config("auth.default_guard", "session"))
        return "session"

    def guard(self, name: str | None = None) -> GuardDriver:
        driver: GuardDriver = self.driver(name)
        return driver

    def create_session_driver(self) -> SessionGuard:
        return SessionGuard()

    def create_local_driver(self) -> LocalGuard:
        return LocalGuard(_db_credential_lookup)

    def create_oidc_driver(self) -> Any:
        """The OIDC/Keycloak guard, built from ``auth.oidc`` config (lazy — keeps core light)."""
        from arvel.auth.oidc import OidcGuard, jwks_verifier

        config: dict[str, Any] = {}
        if self.app is not None and hasattr(self.app, "config"):
            raw = self.app.config("auth.oidc")
            if isinstance(raw, dict):
                config = cast("dict[str, Any]", raw)
        # fail loud here, rather than build a verifier that silently rejects every token
        missing = [key for key in ("jwks_uri", "issuer", "audience") if not config.get(key)]
        if missing:
            raise ValueError(f"auth.oidc is missing required keys: {', '.join(missing)}")
        verifier = jwks_verifier(
            jwks_uri=str(config["jwks_uri"]),
            issuer=str(config["issuer"]),
            audience=str(config["audience"]),
        )
        return OidcGuard(verifier, provider=str(config.get("provider", "oidc")))
