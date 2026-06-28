"""arvel.auth.identity — the identity layer: ``Principal``, ``AuthIdentity``, ``UserProvider``.

Decouples *who a user is* (the durable ``User`` + ``AuthIdentity`` links) from *how they
authenticate* (guard drivers, a follow-on). A guard produces a method-agnostic ``Principal``;
``UserProvider.resolve`` translates it to a ``User`` via the ``auth_identities`` table, applying
the linking / JIT / lockout policy. The IdP's ``sub`` becomes an ``AuthIdentity.subject`` — it is
never an arvel noun. Grounded in DR-0009 / DR-0010 / DR-0012 and
projects/arvel/architecture/auth-rearchitecture.md.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar, Protocol, runtime_checkable

from arvel.database import Model


@dataclass(frozen=True)
class Principal:
    """The method-agnostic result of a guard verification.

    ``subject`` is the IdP-stable identifier (the OIDC ``sub`` / the local credential's
    identifier), **never** the email — emails change, subjects do not.
    """

    provider: str
    subject: str
    claims: Mapping[str, Any] = field(default_factory=dict[str, Any])

    @property
    def email(self) -> str | None:
        value = self.claims.get("email")
        return str(value) if value is not None else None

    @property
    def email_verified(self) -> bool:
        # Defense-in-depth: some IdPs emit a string "true"/"false" — don't let "false" coerce True.
        value = self.claims.get("email_verified", False)
        if isinstance(value, str):
            return value.strip().lower() == "true"
        return bool(value)


class AuthIdentity(Model):
    """A link between an external ``(provider, subject)`` and a local user.

    One ``User`` may have many ``AuthIdentity`` rows (account linking). ``credential`` holds
    the hashed secret for the ``local`` provider and is empty for federated providers.
    """

    __table_name__ = "auth_identities"
    __fields__: ClassVar[dict[str, Any]] = {
        "provider": str,
        "subject": str,
        "user_id": int,
        "credential": str,
    }
    __fillable__: ClassVar[list[str]] = ["provider", "subject", "user_id", "credential"]


class LastCredentialError(RuntimeError):
    """Raised when unlinking would leave a user with no way to authenticate (DR-0012)."""


@runtime_checkable
class IdentityStore(Protocol):
    """The persistence seam ``UserProvider`` resolves through.

    The default implementation is DB-backed (``AuthIdentity`` + the app's ``User`` model);
    tests inject an in-memory fake so the security policy is unit-testable without a database.
    """

    async def find(self, provider: str, subject: str) -> Any | None: ...
    async def user_for(self, identity: Any) -> Any | None: ...
    async def user_by_email(self, email: str) -> Any | None: ...
    async def link(
        self, principal: Principal, user: Any, *, credential: str | None = None
    ) -> Any: ...
    async def count_for_user(self, user: Any) -> int: ...
    async def unlink(self, user: Any, provider: str, subject: str) -> None: ...


class UserProvider:
    """Resolve a verified ``Principal`` to a ``User`` via the identity store.

    Policy (DR-0010 / DR-0012):
      1. A known ``(provider, subject)`` resolves to its linked user.
      2. An unknown identity links to an existing user **only** when the IdP asserts a
         *verified* email **and** the provider is configured-trusted to assert it — the
         account-takeover boundary.
      3. Otherwise, just-in-time provisioning if (and only if) it is enabled.
      4. Else, no safe resolution → ``None``.
    Unlinking can never remove a user's last remaining credential.
    """

    def __init__(
        self,
        store: IdentityStore,
        *,
        trusted_email_providers: set[str] | None = None,
        jit: bool = False,
        user_factory: Any = None,
    ) -> None:
        self._store = store
        self._trusted = set(trusted_email_providers or set())
        self._jit = jit
        self._user_factory = user_factory

    async def resolve(self, principal: Principal) -> Any | None:
        # 1. Known identity → that user.
        identity = await self._store.find(principal.provider, principal.subject)
        if identity is not None:
            return await self._store.user_for(identity)

        # 2. Link to an existing user ONLY on verified email from a trusted provider (DR-0010).
        if principal.email_verified and principal.provider in self._trusted and principal.email:
            user = await self._store.user_by_email(principal.email)
            if user is not None:
                await self._store.link(principal, user)
                return user

        # 3. Just-in-time provisioning — opt-in only.
        if self._jit and self._user_factory is not None:
            user = await self._user_factory(principal)
            await self._store.link(principal, user)
            return user

        # 4. No safe resolution.
        return None

    async def unlink(self, user: Any, provider: str, subject: str) -> None:
        # DR-0012: never remove a user's last remaining credential.
        if await self._store.count_for_user(user) <= 1:
            raise LastCredentialError(
                "Cannot unlink the last remaining authentication method for this user."
            )
        await self._store.unlink(user, provider, subject)


class DbIdentityStore:
    """The default DB-backed :class:`IdentityStore` over :class:`AuthIdentity` + the app's user model.

    ``user_model`` is the application's ``User`` (arvel doesn't own it — the app passes its class).
    """

    def __init__(self, user_model: type[Any]) -> None:
        self._user_model = user_model

    async def find(self, provider: str, subject: str) -> Any | None:
        return await AuthIdentity.where(provider=provider, subject=subject).first()

    async def user_for(self, identity: Any) -> Any | None:
        return await self._user_model.find(identity.user_id)

    async def user_by_email(self, email: str) -> Any | None:
        return await self._user_model.where(email=email).first()

    async def link(self, principal: Principal, user: Any, *, credential: str | None = None) -> Any:
        return await AuthIdentity.create(
            provider=principal.provider,
            subject=principal.subject,
            user_id=user.id,
            credential=credential or "",
        )

    async def count_for_user(self, user: Any) -> int:
        rows = await AuthIdentity.where(user_id=user.id).get()
        return len(rows)

    async def unlink(self, user: Any, provider: str, subject: str) -> None:
        record = await AuthIdentity.where(provider=provider, subject=subject).first()
        if record is not None and record.user_id == user.id:
            await record.delete()
