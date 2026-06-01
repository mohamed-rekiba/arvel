"""AuthService guards that don't touch the database: secret check, token decode, accessor."""

from __future__ import annotations

import importlib
import time

import pytest
from arvel.auth.auth_service import AuthService, get_auth_service, set_current
from arvel.auth.config import JwtConfig
from arvel.auth.exceptions import InvalidCredentialsError

_SECRET = "s" * 32


def _service() -> AuthService:
    return AuthService(jwt=JwtConfig(secret=_SECRET, algorithm="HS256", ttl_seconds=300))


def _encode(payload: dict[str, object]) -> str:
    jwt_mod = importlib.import_module("jwt")
    return str(jwt_mod.encode(payload, _SECRET, algorithm="HS256"))


def test_requires_a_jwt_secret() -> None:
    # model_construct skips JwtConfig's min-length validator so we can hit the
    # service-level guard directly.
    blank = JwtConfig.model_construct(secret="")
    with pytest.raises(ValueError, match="jwt_secret is required"):
        AuthService(jwt=blank)


async def test_me_rejects_wrong_token_typ() -> None:
    token = _encode({"sub": "u1", "exp": int(time.time()) + 300, "typ": "refresh"})
    with pytest.raises(InvalidCredentialsError, match="invalid access token"):
        await _service().me(access_token=token)


async def test_me_rejects_garbage_token() -> None:
    with pytest.raises(InvalidCredentialsError, match="invalid access token"):
        await _service().me(access_token="not-a-jwt")


def test_get_auth_service_unbound_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import arvel.auth.auth_service as mod

    monkeypatch.setattr(mod, "_current", None)
    with pytest.raises(RuntimeError, match="not bound"):
        get_auth_service()


def test_set_current_binds_accessor(monkeypatch: pytest.MonkeyPatch) -> None:
    import arvel.auth.auth_service as mod

    monkeypatch.setattr(mod, "_current", None)
    service = _service()
    set_current(service)
    assert get_auth_service() is service
