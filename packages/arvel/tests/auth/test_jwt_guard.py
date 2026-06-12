"""
JwtGuard moved to arvel.auth, Python-2 except bug fixed.
Tests import from arvel.auth.guards.jwt → red state.
"""

from __future__ import annotations

from typing import Any

import pytest
from arvel.auth.config import JwtConfig

# JWT support is via the [jwt] extra. SKIP cleanly when missing.
pytest.importorskip("jwt", reason="install arvel[jwt] to run JWT guard tests")

_SECRET = "a" * 32  # 32-byte HMAC secret (minimum valid)


def _jwt_config(
    *,
    secret: str = _SECRET,
    algorithm: str = "HS256",
) -> JwtConfig:
    return JwtConfig(secret=secret, algorithm=algorithm)


class _FakeResolver:
    def __init__(self, users: dict[str, Any] | None = None) -> None:
        self._users = users or {}

    async def by_id(self, user_id: str) -> Any | None:
        return self._users.get(user_id)

    async def by_credentials(self, credentials: dict[str, object]) -> Any | None:
        return None


def _make_token(
    sub: str,
    secret: str = _SECRET,
    algorithm: str = "HS256",
    exp_offset: int = 3600,
    *,
    typ: str = "access",
) -> str:
    import importlib
    import time

    _jwt = importlib.import_module("jwt")
    return str(
        _jwt.encode(
            {"sub": sub, "exp": int(time.time()) + exp_offset, "typ": typ},
            secret,
            algorithm=algorithm,
        )
    )


class _FakeRequest:
    def __init__(self, authorization: str | None = None) -> None:
        headers: dict[str, str] = {}
        if authorization:
            headers["authorization"] = authorization
        self.headers = headers


# guard resolves user from valid JWT


@pytest.mark.asyncio
async def test_jwt_guard_resolves_user_from_valid_token() -> None:
    from arvel.auth.guards.jwt import JwtGuard

    token = _make_token("u1")
    resolver = _FakeResolver({"u1": {"id": "u1"}})
    guard = JwtGuard(resolver=resolver, jwt=_jwt_config())
    request = _FakeRequest(authorization=f"Bearer {token}")

    user = await guard.user(request)
    assert user == {"id": "u1"}


@pytest.mark.asyncio
async def test_jwt_guard_returns_none_when_no_authorization_header() -> None:
    from arvel.auth.guards.jwt import JwtGuard

    guard = JwtGuard(resolver=_FakeResolver(), jwt=_jwt_config())
    assert await guard.user(_FakeRequest()) is None


# alg=none refused at construction


def test_jwt_guard_refuses_alg_none() -> None:
    from arvel.auth.guards.jwt import JwtGuard

    with pytest.raises(ValueError, match="none"):
        JwtGuard(resolver=_FakeResolver(), jwt=_jwt_config(algorithm="none"))


def test_jwt_guard_refuses_alg_none_case_insensitive() -> None:
    from arvel.auth.guards.jwt import JwtGuard

    with pytest.raises(ValueError, match="none"):
        JwtGuard(resolver=_FakeResolver(), jwt=_jwt_config(algorithm="None"))


# HMAC secret length enforcement


def test_jwt_guard_refuses_short_hmac_secret() -> None:
    from arvel.auth.guards.jwt import JwtGuard

    with pytest.raises(ValueError, match="32"):
        JwtGuard(resolver=_FakeResolver(), jwt=_jwt_config(secret="tooshort"))


def test_jwt_guard_accepts_32_byte_hmac_secret() -> None:
    from arvel.auth.guards.jwt import JwtGuard

    guard = JwtGuard(resolver=_FakeResolver(), jwt=_jwt_config(algorithm="HS256"))
    assert guard is not None


# expired token returns None


@pytest.mark.asyncio
async def test_jwt_guard_rejects_expired_token() -> None:
    from arvel.auth.guards.jwt import JwtGuard

    token = _make_token("u1", exp_offset=-10)
    guard = JwtGuard(resolver=_FakeResolver({"u1": {"id": "u1"}}), jwt=_jwt_config())
    request = _FakeRequest(authorization=f"Bearer {token}")

    assert await guard.user(request) is None


# invalid signature returns None


@pytest.mark.asyncio
async def test_jwt_guard_rejects_tampered_signature() -> None:
    from arvel.auth.guards.jwt import JwtGuard

    token = _make_token("u1") + "tampered"
    guard = JwtGuard(resolver=_FakeResolver({"u1": {"id": "u1"}}), jwt=_jwt_config())
    request = _FakeRequest(authorization=f"Bearer {token}")

    assert await guard.user(request) is None


# wrong secret returns None


@pytest.mark.asyncio
async def test_jwt_guard_rejects_token_signed_with_different_secret() -> None:
    from arvel.auth.guards.jwt import JwtGuard

    other_secret = "b" * 32
    token = _make_token("u1", secret=other_secret)
    guard = JwtGuard(resolver=_FakeResolver({"u1": {"id": "u1"}}), jwt=_jwt_config())
    request = _FakeRequest(authorization=f"Bearer {token}")

    assert await guard.user(request) is None


# Multi-exception handler uses the bare tuple form (parens not required in 3.14)


def test_jwt_guard_uses_bare_except_tuple() -> None:
    """jwt.py uses the bare `except A, B:` form — a valid tuple-catch in Python
    3.14, so the parentheses are not required."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.find_spec("arvel.auth.guards.jwt")
    assert spec is not None and spec.origin is not None
    source = Path(spec.origin).read_text(encoding="utf-8")
    assert "except TypeError, ValueError:" in source
    assert "except (TypeError, ValueError):" not in source


# malformed authorization header returns None


@pytest.mark.asyncio
async def test_jwt_guard_returns_none_for_non_bearer_scheme() -> None:
    from arvel.auth.guards.jwt import JwtGuard

    guard = JwtGuard(resolver=_FakeResolver(), jwt=_jwt_config())
    request = _FakeRequest(authorization="Basic dXNlcjpwYXNz")

    assert await guard.user(request) is None


@pytest.mark.asyncio
async def test_jwt_guard_handles_malformed_headers_object_without_crashing() -> None:
    from arvel.auth.guards.jwt import JwtGuard

    class _BadHeaders:
        def __iter__(self) -> None:
            raise TypeError("not iterable")

    class _BadRequest:
        headers = _BadHeaders()

    guard = JwtGuard(resolver=_FakeResolver(), jwt=_jwt_config())
    assert await guard.user(_BadRequest()) is None


# issue_token / _encode round-trip


@pytest.mark.asyncio
async def test_jwt_guard_issued_token_round_trips() -> None:
    from datetime import timedelta

    from arvel.auth.guards.jwt import JwtGuard

    config = JwtConfig(
        secret=_SECRET, algorithm="HS256", audience="arvel-api", issuer="https://issuer.test"
    )
    resolver = _FakeResolver({"u1": {"id": "u1"}})
    guard = JwtGuard(resolver=resolver, jwt=config)

    token = await guard.issue_token(subject="u1", expires_in=timedelta(minutes=5))
    request = _FakeRequest(authorization=f"Bearer {token}")
    assert await guard.user(request) == {"id": "u1"}


@pytest.mark.asyncio
async def test_jwt_guard_rejects_refresh_typed_token() -> None:
    import importlib
    import time

    from arvel.auth.guards.jwt import JwtGuard

    _jwt = importlib.import_module("jwt")
    token = str(
        _jwt.encode(
            {"sub": "u1", "exp": int(time.time()) + 3600, "typ": "refresh"},
            _SECRET,
            algorithm="HS256",
        )
    )
    guard = JwtGuard(resolver=_FakeResolver({"u1": {"id": "u1"}}), jwt=_jwt_config())
    request = _FakeRequest(authorization=f"Bearer {token}")
    assert await guard.user(request) is None


@pytest.mark.asyncio
async def test_jwt_guard_rejects_token_without_sub() -> None:
    import importlib
    import time

    from arvel.auth.guards.jwt import JwtGuard

    _jwt = importlib.import_module("jwt")
    token = str(_jwt.encode({"exp": int(time.time()) + 3600}, _SECRET, algorithm="HS256"))
    guard = JwtGuard(resolver=_FakeResolver(), jwt=_jwt_config())
    request = _FakeRequest(authorization=f"Bearer {token}")
    assert await guard.user(request) is None


@pytest.mark.asyncio
async def test_jwt_guard_rejects_suspended_user() -> None:
    """A valid, unexpired token for a suspended account resolves to None."""
    from datetime import UTC, datetime

    from arvel.auth.guards.jwt import JwtGuard
    from arvel.auth.mixins import Authenticatable

    class _SuspendedUser(Authenticatable):
        id = "u1"
        suspended_at = datetime(2020, 1, 1, tzinfo=UTC)

    token = _make_token("u1")
    guard = JwtGuard(resolver=_FakeResolver({"u1": _SuspendedUser()}), jwt=_jwt_config())
    request = _FakeRequest(authorization=f"Bearer {token}")
    assert await guard.user(request) is None


# ── A2: JwtGuard rejects tokens where typ claim is missing ────────────────────


@pytest.mark.asyncio
async def test_jwt_guard_rejects_token_with_missing_typ_claim() -> None:
    """A token without a typ claim must be rejected (not just a wrong typ)."""
    import importlib
    import time

    from arvel.auth.guards.jwt import JwtGuard

    _jwt = importlib.import_module("jwt")
    # Valid token but no typ claim at all — must be rejected.
    token = str(
        _jwt.encode(
            {"sub": "u1", "exp": int(time.time()) + 3600},
            _SECRET,
            algorithm="HS256",
        )
    )
    guard = JwtGuard(resolver=_FakeResolver({"u1": {"id": "u1"}}), jwt=_jwt_config())
    request = _FakeRequest(authorization=f"Bearer {token}")
    assert await guard.user(request) is None


@pytest.mark.asyncio
async def test_jwt_guard_rejects_refresh_token_as_access() -> None:
    """A refresh token (typ='refresh') must not authenticate a request."""
    import importlib
    import time

    from arvel.auth.guards.jwt import JwtGuard

    _jwt = importlib.import_module("jwt")
    token = str(
        _jwt.encode(
            {"sub": "u1", "exp": int(time.time()) + 3600, "typ": "refresh"},
            _SECRET,
            algorithm="HS256",
        )
    )
    guard = JwtGuard(resolver=_FakeResolver({"u1": {"id": "u1"}}), jwt=_jwt_config())
    request = _FakeRequest(authorization=f"Bearer {token}")
    assert await guard.user(request) is None
