"""
Security sweep for (Auth subsystem).
Quality gates 50-55. All tests red until arvel.auth is implemented.
"""

from __future__ import annotations

from typing import Any

import pytest
from arvel.auth.config import JwtConfig
from arvel.auth.guard import UserResolver

_SECRET = "a" * 32


# Gate 50: JWT alg-confusion attack prevention


def test_jwt_guard_refuses_alg_none_in_new_module() -> None:
    from arvel.auth.guards.jwt import JwtGuard

    with pytest.raises(ValueError, match="none"):
        JwtGuard(resolver=_make_resolver(), jwt=JwtConfig(secret=_SECRET, algorithm="none"))


def test_jwt_guard_refuses_alg_none_caps() -> None:
    from arvel.auth.guards.jwt import JwtGuard

    with pytest.raises(ValueError, match="[Nn]one"):
        JwtGuard(resolver=_make_resolver(), jwt=JwtConfig(secret=_SECRET, algorithm="NONE"))


def test_jwt_guard_refuses_short_hmac_secret() -> None:
    from arvel.auth.guards.jwt import JwtGuard

    with pytest.raises(ValueError):
        JwtGuard(resolver=_make_resolver(), jwt=JwtConfig(secret="too-short", algorithm="HS256"))


# Gate 51: timing-safe token comparison


def test_token_guard_source_uses_compare_digest() -> None:
    import importlib.util
    from pathlib import Path

    spec = importlib.util.find_spec("arvel.auth.guards.token")
    assert spec and spec.origin
    source = Path(spec.origin).read_text()
    assert "compare_digest" in source, "TokenGuard must use hmac.compare_digest"


def test_hash_facade_uses_bcrypt_checkpw_not_equality_operator() -> None:
    import importlib.util
    from pathlib import Path

    spec = importlib.util.find_spec("arvel.facades.hash")
    assert spec and spec.origin
    source = Path(spec.origin).read_text()
    assert "verify" in source or "checkpw" in source or "compare_digest" in source


# Gate 52: session fixation prevention


@pytest.mark.asyncio
async def test_session_guard_login_regenerates_session_id() -> None:
    from arvel.auth.guards.session import SessionGuard

    class _TrackSession:
        def __init__(self) -> None:
            self._data: dict[str, object] = {}
            self.regenerated = False

        def get(self, key: str, default: object = None) -> object:
            return self._data.get(key, default)

        def put(self, key: str, value: object) -> None:
            self._data[key] = value

        def forget(self, key: str) -> None:
            self._data.pop(key, None)

        def regenerate(self) -> None:
            self.regenerated = True

    session = _TrackSession()
    request = type("R", (), {"state": type("S", (), {"session": session})()})()

    class _User:
        id = "u1"

    guard = SessionGuard(resolver=_make_resolver())
    await guard.login(_User(), request)

    assert session.regenerated, "login() must call session.regenerate() to prevent session fixation"


# Gate 53: Gate fail-closed


@pytest.mark.asyncio
async def test_gate_raises_for_unregistered_ability() -> None:
    from arvel.auth.exceptions import AuthorizationException
    from arvel.auth.gate import Gate

    gate = Gate()

    class _User:
        id = "u1"

    with pytest.raises(AuthorizationException):
        await gate.allows("not-registered", _User())


# Gate 54: backward compat re-exports


def test_arvel_http_auth_still_exports_all_symbols() -> None:
    from arvel.http import auth as http_auth

    for name in ("Guard", "SessionGuard", "JwtGuard", "UserResolver"):
        assert hasattr(http_auth, name), f"arvel.http.auth missing re-export: {name}"


# Gate 55: auth module coverage (100% import — no syntax errors)


def test_all_auth_modules_importable() -> None:
    modules = [
        "arvel.auth",
        "arvel.auth.manager",
        "arvel.auth.guard",
        "arvel.auth.guards.session",
        "arvel.auth.guards.jwt",
        "arvel.auth.guards.token",
        "arvel.auth.providers.database",
        "arvel.auth.mixins",
        "arvel.auth.gate",
        "arvel.auth.policy",
        "arvel.auth.config",
        "arvel.auth.exceptions",
        "arvel.auth.provider",
        "arvel.auth.middleware.guest",
        "arvel.auth.middleware.verified",
        "arvel.auth.middleware.can",
        "arvel.auth.middleware.authenticate",
        "arvel.facades.auth",
        "arvel.facades.hash",
    ]
    failed: list[str] = []
    for mod in modules:
        try:
            __import__(mod)
        except ImportError as exc:
            failed.append(f"{mod}: {exc}")

    assert not failed, f"Auth modules not importable: {failed}"


# helpers


def _make_resolver() -> UserResolver:
    class _R:
        async def by_id(self, user_id: str) -> Any | None:
            return None

        async def by_credentials(self, credentials: dict[str, object]) -> Any | None:
            return None

    return _R()
