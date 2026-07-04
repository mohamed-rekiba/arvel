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
    """Reflects the established session — a ``Principal`` for the ``current_user``, else ``None``."""

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
