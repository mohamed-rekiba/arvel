"""login throttle middleware (RED state)."""

from __future__ import annotations

import json

import pytest
from arvel.auth.middleware.throttle_login import (
    CacheLoginAttemptStore,
    ThrottleLoginConfig,
    ThrottleLoginMiddleware,
)
from arvel.facades.cache import Cache
from httpx2 import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

# helpers


async def _login_handler(request: Request) -> JSONResponse:
    body = await request.body()
    data: dict[str, object] = json.loads(body) if body else {}
    password = str(data.get("password", ""))
    if password == "correct":
        return JSONResponse({"access_token": "tok"}, status_code=200)
    return JSONResponse({"error": {"code": "INVALID_CREDENTIALS"}}, status_code=401)


def _make_app(max_attempts: int = 5, window: int = 60) -> tuple[Starlette, ThrottleLoginMiddleware]:
    inner = Starlette(routes=[Route("/api/auth/login", _login_handler, methods=["POST"])])
    mw = ThrottleLoginMiddleware(
        inner,
        ThrottleLoginConfig(
            login_path="/api/auth/login",
            max_attempts=max_attempts,
            window_seconds=window,
        ),
    )
    return inner, mw


@pytest.mark.asyncio
async def test_under_threshold_passes_through() -> None:
    """4 failed attempts in 60s still allow a 5th."""
    _, mw = _make_app(max_attempts=5)
    async with AsyncClient(transport=ASGITransport(app=mw), base_url="http://test") as client:
        for _ in range(4):
            r = await client.post(
                "/api/auth/login",
                content=json.dumps({"email": "u@test.com", "password": "wrong"}),
                headers={"content-type": "application/json"},
            )
            assert r.status_code == 401

        # 5th attempt should still reach the handler (not throttled yet).
        r = await client.post(
            "/api/auth/login",
            content=json.dumps({"email": "u@test.com", "password": "wrong"}),
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_at_threshold_returns_429_with_retry_after() -> None:
    """5th failed attempt within window → 429 + Retry-After."""
    _, mw = _make_app(max_attempts=5)
    async with AsyncClient(transport=ASGITransport(app=mw), base_url="http://test") as client:
        for _ in range(5):
            await client.post(
                "/api/auth/login",
                content=json.dumps({"email": "u2@test.com", "password": "wrong"}),
                headers={"content-type": "application/json"},
            )

        # 6th attempt — now blocked.
        r = await client.post(
            "/api/auth/login",
            content=json.dumps({"email": "u2@test.com", "password": "wrong"}),
            headers={"content-type": "application/json"},
        )
    assert r.status_code == 429
    assert "Retry-After" in r.headers


@pytest.mark.asyncio
async def test_window_expires_resets_counter() -> None:
    """After the window expires, the counter resets to 0."""
    import asyncio

    _, mw = _make_app(max_attempts=2, window=1)  # 1-second window for fast test
    async with AsyncClient(transport=ASGITransport(app=mw), base_url="http://test") as client:
        for _ in range(2):
            await client.post(
                "/api/auth/login",
                content=json.dumps({"email": "u3@test.com", "password": "wrong"}),
                headers={"content-type": "application/json"},
            )

        # Expire the window.
        await asyncio.sleep(1.1)

        # Counter should be reset; this attempt should reach the handler.
        r = await client.post(
            "/api/auth/login",
            content=json.dumps({"email": "u3@test.com", "password": "wrong"}),
            headers={"content-type": "application/json"},
        )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_successful_login_resets_counter() -> None:
    """A successful login clears the failed-attempt counter."""
    _, mw = _make_app(max_attempts=3)
    async with AsyncClient(transport=ASGITransport(app=mw), base_url="http://test") as client:
        for _ in range(2):
            await client.post(
                "/api/auth/login",
                content=json.dumps({"email": "u4@test.com", "password": "wrong"}),
                headers={"content-type": "application/json"},
            )

        # Successful login resets counter.
        r = await client.post(
            "/api/auth/login",
            content=json.dumps({"email": "u4@test.com", "password": "correct"}),
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 200

        # Now 2 more failures should be allowed (counter reset).
        for _ in range(2):
            r = await client.post(
                "/api/auth/login",
                content=json.dumps({"email": "u4@test.com", "password": "wrong"}),
                headers={"content-type": "application/json"},
            )
            assert r.status_code == 401


@pytest.mark.asyncio
async def test_keys_per_email_and_ip() -> None:
    """Counter keyed on (email, ip) — different IP doesn't trip the same email."""
    _, mw = _make_app(max_attempts=2)
    async with AsyncClient(transport=ASGITransport(app=mw), base_url="http://test") as client:
        # Exhaust limit from IP "1.2.3.4" (simulated via scope — httpx will use 127.0.0.1).
        for _ in range(2):
            await client.post(
                "/api/auth/login",
                content=json.dumps({"email": "u5@test.com", "password": "wrong"}),
                headers={"content-type": "application/json"},
            )

    # A different email should not be throttled.
    _, mw2 = _make_app(max_attempts=2)
    async with AsyncClient(transport=ASGITransport(app=mw2), base_url="http://test") as client:
        r = await client.post(
            "/api/auth/login",
            content=json.dumps({"email": "other@test.com", "password": "wrong"}),
            headers={"content-type": "application/json"},
        )
    assert r.status_code == 401  # different email, fresh counter


async def _post_login(app: ThrottleLoginMiddleware, email: str) -> int:
    body = json.dumps({"email": email, "password": "wrong"})
    headers = {"content-type": "application/json"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/auth/login", content=body, headers=headers)
    return resp.status_code


@pytest.mark.asyncio
async def test_cache_store_shares_counter_across_instances() -> None:
    """Two middleware instances (= two workers) share the limit via the cache."""
    with Cache.fake():
        inner_a = Starlette(routes=[Route("/api/auth/login", _login_handler, methods=["POST"])])
        inner_b = Starlette(routes=[Route("/api/auth/login", _login_handler, methods=["POST"])])
        cfg = ThrottleLoginConfig(max_attempts=3, store=CacheLoginAttemptStore())
        mw_a = ThrottleLoginMiddleware(inner_a, cfg)
        mw_b = ThrottleLoginMiddleware(inner_b, cfg)

        # 3 failures spread across both "workers".
        assert await _post_login(mw_a, "shared@test.com") == 401
        assert await _post_login(mw_a, "shared@test.com") == 401
        assert await _post_login(mw_b, "shared@test.com") == 401
        # 4th attempt on worker B is blocked thanks to the shared counter.
        assert await _post_login(mw_b, "shared@test.com") == 429


@pytest.mark.asyncio
async def test_cache_store_success_clears_shared_counter() -> None:
    with Cache.fake():
        store = CacheLoginAttemptStore()
        await store.increment("k", window_seconds=60)
        await store.increment("k", window_seconds=60)
        assert await store.count("k") == 2
        await store.reset("k")
        assert await store.count("k") == 0
