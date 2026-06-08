"""HTTP-layer security regressions — ."""

from __future__ import annotations

import inspect
import logging
import time
from typing import Any, cast

import httpx2 as httpx
import pytest
from arvel.auth.config import JwtConfig

#  Safe defaults


def test_cors_rejects_wildcard_with_credentials() -> None:
    from arvel.http.middleware import Cors
    from fastapi import FastAPI

    with pytest.raises(ValueError, match="(?i)wildcard"):
        Cors(FastAPI(), allowed_origins=["*"], allow_credentials=True)


def test_csrf_uses_constant_time_compare() -> None:
    from arvel.http.middleware import VerifyCsrf

    assert "constant_time_equals" in inspect.getsource(VerifyCsrf)


def test_jwt_guard_rejects_alg_none() -> None:
    from arvel.http.auth import JwtGuard

    class _R:
        async def by_id(self, user_id: str) -> Any | None:
            _ = user_id
            return None

        async def by_credentials(self, credentials: dict[str, object]) -> Any | None:
            _ = credentials
            return None

    with pytest.raises(ValueError, match="(?i)none"):
        JwtGuard(resolver=_R(), jwt=JwtConfig(secret="k" * 32, algorithm="none"))


def test_jwt_guard_rejects_short_hmac_secret() -> None:
    from arvel.http.auth import JwtGuard

    class _R:
        async def by_id(self, user_id: str) -> Any | None:
            _ = user_id
            return None

        async def by_credentials(self, credentials: dict[str, object]) -> Any | None:
            _ = credentials
            return None

    with pytest.raises(ValueError, match="(?i)32"):
        JwtGuard(resolver=_R(), jwt=JwtConfig(secret="too-short"))


#  HttpExceptionHandler never leaks stack traces


def test_500_response_does_not_contain_stack_trace() -> None:
    from arvel.http.exceptions import HttpExceptionHandler, ServerErrorException
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    fa = FastAPI()
    HttpExceptionHandler().register(fa)

    @fa.get("/explode")
    async def boom() -> dict[str, str]:
        raise ServerErrorException("kaboom")

    del boom  # registered via @fa.get; drop local binding
    body = (
        cast("httpx.Client", TestClient(fa))
        .get("/explode", headers={"Accept": "application/json"})
        .text
    )
    for forbidden in ("Traceback", 'File "', "raise ServerErrorException"):
        assert forbidden not in body


#  Log redaction


def test_exception_handler_logs_redact_authorization_header(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from arvel.http.exceptions import HttpExceptionHandler, UnauthenticatedException
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    fa = FastAPI()
    HttpExceptionHandler().register(fa)

    @fa.get("/me")
    async def me() -> dict[str, str]:
        raise UnauthenticatedException("no auth")

    del me  # registered via @fa.get; drop local binding
    caplog.set_level(logging.WARNING)
    cast("httpx.Client", TestClient(fa)).get(
        "/me",
        headers={
            "Authorization": "Bearer sk-very-secret-token-do-not-log",
            "Cookie": "session=secret-cookie-value",
        },
    )

    full_log = "\n".join(r.getMessage() for r in caplog.records)
    assert "sk-very-secret-token-do-not-log" not in full_log
    assert "secret-cookie-value" not in full_log


#  OWASP A07 / A09 patterns


def test_throttle_uses_constant_time_key_hashing_for_redis() -> None:
    """RedisStore key hashing should be HMAC-style or hashed — never raw user input."""
    from arvel.http.ratelimit import RedisStore

    src = inspect.getsource(RedisStore)
    # We're not picky about which algo, just that the key is hashed or scoped, not raw.
    assert any(token in src for token in ("hashlib", "hmac", "sha", "blake")), (
        "RedisStore must hash the rate-limit key before sending it to Redis"
    )


def test_jwt_guard_with_audience_rejects_wrong_aud() -> None:
    _jwt = pytest.importorskip("jwt", reason="install arvel[jwt] to run this test")
    from arvel.http.auth import JwtGuard

    class _R:
        async def by_id(self, user_id: str) -> Any | None:
            return {"id": user_id}

        async def by_credentials(self, credentials: dict[str, object]) -> Any | None:
            _ = credentials
            return None

    secret = "k" * 32
    guard = JwtGuard(
        resolver=_R(),
        jwt=JwtConfig(secret=secret, audience="my-api"),
    )
    token = _jwt.encode(
        {"sub": "u-1", "aud": "different-api", "exp": int(time.time()) + 3600},
        secret,
        algorithm="HS256",
    )

    class _Req:
        headers = {"authorization": f"Bearer {token}"}

    import asyncio

    user = asyncio.run(guard.user(_Req()))
    assert user is None
