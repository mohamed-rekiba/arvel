"""+ — JwtGuard."""

from __future__ import annotations

import time
from typing import Any

import pytest
from arvel.auth.config import JwtConfig

# JWT support is via the [jwt] extra. SKIP cleanly when missing.
pytest.importorskip("jwt", reason="install arvel[jwt] to run JWT guard tests")


class _FakeResolver:
    def __init__(self, users: dict[str, dict[str, Any]]) -> None:
        self._users = users

    async def by_id(self, user_id: str) -> Any | None:
        return self._users.get(user_id)

    async def by_credentials(self, credentials: dict[str, object]) -> Any | None:
        return None


class _FakeRequest:
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}


def _jwt_config(
    *,
    secret: str = "k" * 32,
    algorithm: str = "HS256",
) -> JwtConfig:
    return JwtConfig(secret=secret, algorithm=algorithm)


def _make_token(payload: dict[str, Any], secret: str = "k" * 32, alg: str = "HS256") -> str:
    import importlib

    _jwt = importlib.import_module("jwt")
    return str(_jwt.encode(payload, secret, algorithm=alg))


@pytest.mark.asyncio
async def test_jwt_guard_returns_user_for_valid_token() -> None:
    from arvel.http.auth import JwtGuard

    resolver = _FakeResolver({"u-1": {"id": "u-1"}})
    secret = "k" * 32
    guard = JwtGuard(resolver=resolver, jwt=_jwt_config(secret=secret))
    token = _make_token({"sub": "u-1", "exp": int(time.time()) + 3600}, secret=secret)
    request = _FakeRequest(headers={"authorization": f"Bearer {token}"})

    user = await guard.user(request)
    assert user == {"id": "u-1"}


@pytest.mark.asyncio
async def test_jwt_guard_returns_none_for_expired_token() -> None:
    from arvel.http.auth import JwtGuard

    resolver = _FakeResolver({"u-1": {"id": "u-1"}})
    secret = "k" * 32
    guard = JwtGuard(resolver=resolver, jwt=_jwt_config(secret=secret))
    expired = _make_token({"sub": "u-1", "exp": int(time.time()) - 60}, secret=secret)
    request = _FakeRequest(headers={"authorization": f"Bearer {expired}"})

    user = await guard.user(request)
    assert user is None


@pytest.mark.asyncio
async def test_jwt_guard_returns_none_for_tampered_signature() -> None:
    from arvel.http.auth import JwtGuard

    resolver = _FakeResolver({"u-1": {"id": "u-1"}})
    secret = "k" * 32
    guard = JwtGuard(resolver=resolver, jwt=_jwt_config(secret=secret))

    token = _make_token({"sub": "u-1", "exp": int(time.time()) + 3600}, secret=secret)
    tampered = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    request = _FakeRequest(headers={"authorization": f"Bearer {tampered}"})

    user = await guard.user(request)
    assert user is None


@pytest.mark.asyncio
async def test_jwt_guard_returns_none_for_missing_header() -> None:
    from arvel.http.auth import JwtGuard

    resolver = _FakeResolver({"u-1": {"id": "u-1"}})
    guard = JwtGuard(resolver=resolver, jwt=_jwt_config())
    request = _FakeRequest(headers={})

    user = await guard.user(request)
    assert user is None


@pytest.mark.asyncio
async def test_jwt_guard_returns_none_for_malformed_header() -> None:
    from arvel.http.auth import JwtGuard

    resolver = _FakeResolver({"u-1": {"id": "u-1"}})
    guard = JwtGuard(resolver=resolver, jwt=_jwt_config())
    request = _FakeRequest(headers={"authorization": "Basic abc"})

    user = await guard.user(request)
    assert user is None


def test_jwt_guard_rejects_short_hmac_secret() -> None:
    """security guardrail: < 32-byte HMAC secret rejected at construction."""
    from arvel.http.auth import JwtGuard

    resolver = _FakeResolver({})

    with pytest.raises(ValueError, match="(?i)32"):
        JwtGuard(resolver=resolver, jwt=_jwt_config(secret="too-short"))


def test_jwt_guard_rejects_alg_none() -> None:
    """: alg=none JWTs MUST be refused."""
    from arvel.http.auth import JwtGuard

    resolver = _FakeResolver({})

    with pytest.raises(ValueError, match="(?i)none"):
        JwtGuard(resolver=resolver, jwt=_jwt_config(algorithm="none"))
