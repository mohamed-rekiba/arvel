"""
FR-007-020..027 — TokenGuard (Sanctum-style personal access tokens).
Tests import from arvel.auth.guards.token → red state.
"""

from __future__ import annotations

import hashlib
from datetime import UTC
from typing import Any

import pytest


def _sha256(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


class _FakeToken:
    def __init__(
        self,
        token: str,
        tokenable_type: str,
        tokenable_id: str,
        abilities: list[str],
        expires_at: Any = None,
    ) -> None:
        self.token = token
        self.tokenable_type = tokenable_type
        self.tokenable_id = tokenable_id
        self.abilities = abilities
        self.expires_at = expires_at
        self.last_used_at: Any = None


class _FakeTokenRepository:
    def __init__(self, tokens: dict[str, _FakeToken] | None = None) -> None:
        self._tokens = tokens or {}

    async def find_by_hash(self, token_hash: str) -> _FakeToken | None:
        return self._tokens.get(token_hash)

    async def touch(self, token: Any) -> None:
        pass


class _FakeUserRepository:
    def __init__(self, users: dict[str, Any] | None = None) -> None:
        self._users = users or {}

    async def find(self, type_: str, id_: str) -> Any | None:
        return self._users.get(f"{type_}:{id_}")


class _FakeRequest:
    def __init__(self, authorization: str | None = None) -> None:
        self.headers: dict[str, str] = {}
        if authorization:
            self.headers["authorization"] = authorization


# ─── FR-007-020: resolves user from valid token ───────────────────────────────


@pytest.mark.asyncio
async def test_token_guard_resolves_user_from_valid_bearer_token() -> None:
    from arvel.auth.guards.token import TokenGuard

    plain = "arvel_test_token_abc123"
    hashed = _sha256(plain)
    tok = _FakeToken(
        token=hashed,
        tokenable_type="app.Models.User.User",
        tokenable_id="1",
        abilities=["*"],
    )
    token_repo = _FakeTokenRepository({hashed: tok})
    user_repo = _FakeUserRepository({"app.Models.User.User:1": {"id": "1"}})
    guard = TokenGuard(token_repository=token_repo, user_repository=user_repo)

    request = _FakeRequest(authorization=f"Bearer {plain}")
    user = await guard.user(request)
    assert user == {"id": "1"}


@pytest.mark.asyncio
async def test_token_guard_returns_none_when_no_authorization() -> None:
    from arvel.auth.guards.token import TokenGuard

    guard = TokenGuard(
        token_repository=_FakeTokenRepository(),
        user_repository=_FakeUserRepository(),
    )
    assert await guard.user(_FakeRequest()) is None


# ─── FR-007-021: uses hmac.compare_digest for timing safety ──────────────────


def test_token_guard_uses_timing_safe_comparison(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guard must import hmac and use compare_digest, not ==."""
    import importlib
    import importlib.util

    source = importlib.util.find_spec("arvel.auth.guards.token")
    assert source and source.origin
    from pathlib import Path

    text = Path(source.origin).read_text()
    assert "compare_digest" in text, "TokenGuard must use hmac.compare_digest"


# ─── FR-007-022: expired token returns None ───────────────────────────────────


@pytest.mark.asyncio
async def test_token_guard_rejects_expired_token() -> None:
    from datetime import datetime

    from arvel.auth.guards.token import TokenGuard

    plain = "arvel_expired_token"
    hashed = _sha256(plain)
    tok = _FakeToken(
        token=hashed,
        tokenable_type="app.Models.User.User",
        tokenable_id="1",
        abilities=["*"],
        expires_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    token_repo = _FakeTokenRepository({hashed: tok})
    user_repo = _FakeUserRepository({"app.Models.User.User:1": {"id": "1"}})
    guard = TokenGuard(token_repository=token_repo, user_repository=user_repo)

    request = _FakeRequest(authorization=f"Bearer {plain}")
    assert await guard.user(request) is None


# ─── FR-007-023: unknown token returns None ───────────────────────────────────


@pytest.mark.asyncio
async def test_token_guard_returns_none_for_unknown_token() -> None:
    from arvel.auth.guards.token import TokenGuard

    guard = TokenGuard(
        token_repository=_FakeTokenRepository({}),
        user_repository=_FakeUserRepository({}),
    )
    request = _FakeRequest(authorization="Bearer unknown_token")
    assert await guard.user(request) is None


# ─── FR-007-024: last_used_at updated on successful auth ─────────────────────


@pytest.mark.asyncio
async def test_token_guard_updates_last_used_at_on_success() -> None:
    from arvel.auth.guards.token import TokenGuard

    plain = "arvel_token_last_used"
    hashed = _sha256(plain)
    tok = _FakeToken(
        token=hashed,
        tokenable_type="app.Models.User.User",
        tokenable_id="1",
        abilities=["*"],
    )

    updated: list[Any] = []

    class _TrackingRepo(_FakeTokenRepository):
        async def touch(self, token: Any) -> None:
            updated.append(token)

    token_repo = _TrackingRepo({hashed: tok})
    user_repo = _FakeUserRepository({"app.Models.User.User:1": {"id": "1"}})
    guard = TokenGuard(token_repository=token_repo, user_repository=user_repo)

    request = _FakeRequest(authorization=f"Bearer {plain}")
    await guard.user(request)
    assert len(updated) == 1


# ─── FR-007-025: can() checks abilities ──────────────────────────────────────


@pytest.mark.asyncio
async def test_token_guard_can_passes_for_wildcard_ability() -> None:
    from arvel.auth.guards.token import TokenGuard

    plain = "arvel_wildcard_token"
    hashed = _sha256(plain)
    tok = _FakeToken(
        token=hashed,
        tokenable_type="app.Models.User.User",
        tokenable_id="1",
        abilities=["*"],
    )
    token_repo = _FakeTokenRepository({hashed: tok})
    user_repo = _FakeUserRepository({"app.Models.User.User:1": {"id": "1"}})
    guard = TokenGuard(token_repository=token_repo, user_repository=user_repo)

    request = _FakeRequest(authorization=f"Bearer {plain}")
    await guard.user(request)
    assert guard.can("write") is True


@pytest.mark.asyncio
async def test_token_guard_can_fails_for_unlisted_ability() -> None:
    from arvel.auth.guards.token import TokenGuard

    plain = "arvel_read_only_token"
    hashed = _sha256(plain)
    tok = _FakeToken(
        token=hashed,
        tokenable_type="app.Models.User.User",
        tokenable_id="1",
        abilities=["read"],
    )
    token_repo = _FakeTokenRepository({hashed: tok})
    user_repo = _FakeUserRepository({"app.Models.User.User:1": {"id": "1"}})
    guard = TokenGuard(token_repository=token_repo, user_repository=user_repo)

    request = _FakeRequest(authorization=f"Bearer {plain}")
    await guard.user(request)
    assert guard.can("write") is False


# ─── FR-007-026: token stored as SHA-256 (not plain text) ────────────────────


@pytest.mark.asyncio
async def test_token_guard_hashes_token_before_lookup() -> None:
    """The repository find_by_hash receives the hex digest, not the plain token."""
    seen_hashes: list[str] = []

    class _TrackingRepo:
        async def find_by_hash(self, token_hash: str) -> None:
            seen_hashes.append(token_hash)

        async def touch(self, token: Any) -> None:
            pass

    from arvel.auth.guards.token import TokenGuard

    guard = TokenGuard(
        token_repository=_TrackingRepo(),
        user_repository=_FakeUserRepository(),
    )
    await guard.user(_FakeRequest(authorization="Bearer plain_text"))

    assert len(seen_hashes) == 1
    assert len(seen_hashes[0]) == 64  # SHA-256 hex is 64 chars
    assert seen_hashes[0] == _sha256("plain_text")


# ─── FR-007-027: non-bearer scheme returns None ───────────────────────────────


@pytest.mark.asyncio
async def test_token_guard_ignores_non_bearer_auth_scheme() -> None:
    from arvel.auth.guards.token import TokenGuard

    guard = TokenGuard(
        token_repository=_FakeTokenRepository(),
        user_repository=_FakeUserRepository(),
    )
    request = _FakeRequest(authorization="Basic dXNlcjpwYXNz")
    assert await guard.user(request) is None
