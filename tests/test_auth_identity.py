"""Identity layer: Principal + UserProvider linking/JIT/lockout policy.

The security policy is unit-tested against an in-memory IdentityStore fake, so no DB is needed.
"""

from __future__ import annotations

from typing import Any

import pytest

from arvel.auth.identity import (
    LastCredentialError,
    Principal,
    UserProvider,
)


class _User:
    def __init__(self, uid: int, email: str) -> None:
        self.id = uid
        self.email = email


class _FakeStore:
    """In-memory IdentityStore: identities are (provider, subject) -> user_id."""

    def __init__(self, users: list[_User] | None = None) -> None:
        self.users: dict[int, _User] = {u.id: u for u in (users or [])}
        self.identities: dict[tuple[str, str], int] = {}
        self._next_uid = max(self.users, default=0) + 1

    async def find(self, provider: str, subject: str) -> Any | None:
        key = (provider, subject)
        return key if key in self.identities else None

    async def user_for(self, identity: Any) -> Any | None:
        return self.users.get(self.identities[identity])

    async def user_by_email(self, email: str) -> Any | None:
        return next((u for u in self.users.values() if u.email == email), None)

    async def link(
        self, principal: Principal, user: _User, *, credential: str | None = None
    ) -> Any:
        self.identities[(principal.provider, principal.subject)] = user.id
        return (principal.provider, principal.subject)

    async def count_for_user(self, user: _User) -> int:
        return sum(1 for uid in self.identities.values() if uid == user.id)

    async def unlink(self, user: _User, provider: str, subject: str) -> None:
        self.identities.pop((provider, subject), None)


def _principal(provider: str, subject: str, **claims: Any) -> Principal:
    return Principal(provider=provider, subject=subject, claims=claims)


# --- Principal ----------------------------------------------------------------


def test_principal_email_helpers() -> None:
    p = _principal("keycloak", "sub-1", email="ada@corp.com", email_verified=True)
    assert p.email == "ada@corp.com"
    assert p.email_verified is True
    bare = _principal("keycloak", "sub-2")
    assert bare.email is None
    assert bare.email_verified is False


# --- resolve: known identity --------------------------------------------------


@pytest.mark.asyncio
async def test_known_identity_resolves_to_its_user() -> None:
    ada = _User(1, "ada@corp.com")
    store = _FakeStore([ada])
    await store.link(_principal("keycloak", "sub-1"), ada)
    provider = UserProvider(store)

    resolved = await provider.resolve(_principal("keycloak", "sub-1"))
    assert resolved is ada


# --- resolve: linking by email --------------------------------------------------


@pytest.mark.asyncio
async def test_links_on_verified_email_from_trusted_provider() -> None:
    ada = _User(1, "ada@corp.com")
    store = _FakeStore([ada])
    provider = UserProvider(store, trusted_email_providers={"keycloak"})

    resolved = await provider.resolve(
        _principal("keycloak", "new-sub", email="ada@corp.com", email_verified=True)
    )
    assert resolved is ada
    # the new identity is now linked to the same user
    assert await store.find("keycloak", "new-sub") is not None


@pytest.mark.asyncio
async def test_does_not_link_on_unverified_email() -> None:
    """The account-takeover boundary: unverified email must never auto-link."""
    ada = _User(1, "ada@corp.com")
    store = _FakeStore([ada])
    provider = UserProvider(store, trusted_email_providers={"keycloak"})

    resolved = await provider.resolve(
        _principal("keycloak", "attacker-sub", email="ada@corp.com", email_verified=False)
    )
    assert resolved is None
    assert await store.find("keycloak", "attacker-sub") is None


@pytest.mark.asyncio
async def test_does_not_link_from_untrusted_provider() -> None:
    ada = _User(1, "ada@corp.com")
    store = _FakeStore([ada])
    provider = UserProvider(store, trusted_email_providers={"keycloak"})  # github NOT trusted

    resolved = await provider.resolve(
        _principal("github", "gh-1", email="ada@corp.com", email_verified=True)
    )
    assert resolved is None


# --- resolve: JIT provisioning ------------------------------------------------


@pytest.mark.asyncio
async def test_jit_provisions_when_enabled() -> None:
    store = _FakeStore()

    async def factory(principal: Principal) -> _User:
        user = _User(99, principal.email or "")
        store.users[user.id] = user
        return user

    provider = UserProvider(store, jit=True, user_factory=factory)
    resolved = await provider.resolve(
        _principal("keycloak", "sub-x", email="new@corp.com", email_verified=True)
    )
    assert resolved is not None
    assert resolved.id == 99
    assert await store.find("keycloak", "sub-x") is not None


@pytest.mark.asyncio
async def test_no_jit_returns_none_for_unknown() -> None:
    provider = UserProvider(_FakeStore())  # jit off by default
    resolved = await provider.resolve(
        _principal("keycloak", "sub-x", email="new@corp.com", email_verified=True)
    )
    assert resolved is None


# --- unlink: last-credential lockout --------------------------------------------


@pytest.mark.asyncio
async def test_unlink_refuses_last_credential() -> None:
    ada = _User(1, "ada@corp.com")
    store = _FakeStore([ada])
    await store.link(_principal("local", "ada@corp.com"), ada)
    provider = UserProvider(store)

    with pytest.raises(LastCredentialError):
        await provider.unlink(ada, "local", "ada@corp.com")
    # still linked — the unlink was refused
    assert await store.find("local", "ada@corp.com") is not None


@pytest.mark.asyncio
async def test_unlink_succeeds_when_another_credential_remains() -> None:
    ada = _User(1, "ada@corp.com")
    store = _FakeStore([ada])
    await store.link(_principal("local", "ada@corp.com"), ada)
    await store.link(_principal("keycloak", "sub-1"), ada)
    provider = UserProvider(store)

    await provider.unlink(ada, "keycloak", "sub-1")
    assert await store.find("keycloak", "sub-1") is None
    assert await store.find("local", "ada@corp.com") is not None
