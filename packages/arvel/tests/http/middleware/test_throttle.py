"""Throttle middleware + RateLimiterStore drivers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest


@pytest.mark.asyncio
async def test_inmemory_store_increments_per_key() -> None:
    from arvel.http.ratelimit import InMemoryStore

    store = InMemoryStore()
    a1 = await store.hit("user:1", decay_seconds=60)
    a2 = await store.hit("user:1", decay_seconds=60)
    a3 = await store.hit("user:2", decay_seconds=60)

    assert a1.count == 1
    assert a2.count == 2
    assert a3.count == 1


@pytest.mark.asyncio
async def test_inmemory_store_resets_after_decay() -> None:
    from arvel.http.ratelimit import InMemoryStore

    store = InMemoryStore()
    a1 = await store.hit("user:1", decay_seconds=0)  # immediate decay
    # Force time to pass — fast-decay test
    a2 = await store.hit("user:1", decay_seconds=0)

    # With decay 0 every hit starts a fresh window
    assert a1.count == 1
    assert a2.count == 1


def test_throttle_middleware_blocks_after_max_attempts() -> None:
    from arvel.http.exceptions import HttpExceptionHandler
    from arvel.http.middleware import Throttle
    from arvel.http.ratelimit import InMemoryStore
    from arvel.routing import Route, Router
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    Router.reset_singleton()

    store = InMemoryStore()
    with Route.group(middleware=[Throttle(3, store=store)]):

        @Route.get("/ping")
        async def ping() -> dict[str, bool]:
            return {"ok": True}

    del ping  # registered via @Route.get; drop local binding
    app = FastAPI()
    HttpExceptionHandler().register(app)
    Router.singleton().register_with_app(app)
    client = TestClient(app)

    # First 3 succeed
    for _ in range(3):
        assert client.get("/ping").status_code == 200

    # 4th is throttled
    resp = client.get("/ping")
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "TOO_MANY_REQUESTS"


def test_throttle_rejects_invalid_max_attempts() -> None:
    from arvel.http.middleware import Throttle

    with pytest.raises(ValueError, match="max_attempts must be >= 1"):
        Throttle(0)


def test_default_key_uses_unknown_without_client() -> None:
    from arvel.http import _middleware_core

    default_key = cast(
        "Callable[[object], str]",
        object.__getattribute__(_middleware_core, "_default_key"),
    )

    assert default_key(SimpleNamespace(client=None)) == "ip:unknown"


def test_default_key_uses_unknown_without_host() -> None:
    from arvel.http import _middleware_core

    default_key = cast(
        "Callable[[object], str]",
        object.__getattribute__(_middleware_core, "_default_key"),
    )

    assert default_key(SimpleNamespace(client=SimpleNamespace(host=""))) == "ip:unknown"


def test_throttle_response_carries_rate_limit_headers() -> None:
    from arvel.http.exceptions import HttpExceptionHandler
    from arvel.http.middleware import Throttle
    from arvel.http.ratelimit import InMemoryStore
    from arvel.routing import Route, Router
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    Router.reset_singleton()

    from starlette.responses import JSONResponse

    store = InMemoryStore()
    with Route.group(middleware=[Throttle(10, store=store)]):

        @Route.get("/ping")
        async def ping() -> JSONResponse:
            return JSONResponse({"ok": True})

    del ping  # registered via @Route.get; drop local binding
    app = FastAPI()
    HttpExceptionHandler().register(app)
    Router.singleton().register_with_app(app)
    resp = TestClient(app).get("/ping")
    assert resp.status_code == 200
    assert "x-ratelimit-limit" in {k.lower() for k in resp.headers}
    assert "x-ratelimit-remaining" in {k.lower() for k in resp.headers}


def test_throttle_429_sends_retry_after() -> None:
    from arvel.http.exceptions import HttpExceptionHandler
    from arvel.http.middleware import Throttle
    from arvel.http.ratelimit import InMemoryStore
    from arvel.routing import Route, Router
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    Router.reset_singleton()

    store = InMemoryStore()
    with Route.group(middleware=[Throttle(1, store=store)]):

        @Route.get("/ping")
        async def ping() -> dict[str, bool]:
            return {"ok": True}

    del ping  # registered via @Route.get; drop local binding
    app = FastAPI()
    HttpExceptionHandler().register(app)
    Router.singleton().register_with_app(app)
    client = TestClient(app)
    client.get("/ping")  # consume the only attempt
    resp = client.get("/ping")
    assert resp.status_code == 429
    assert "retry-after" in {k.lower() for k in resp.headers}


def test_throttle_custom_key_callable() -> None:
    from arvel.http.exceptions import HttpExceptionHandler
    from arvel.http.middleware import Throttle
    from arvel.http.ratelimit import InMemoryStore
    from arvel.routing import Route, Router
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    Router.reset_singleton()

    store = InMemoryStore()

    def user_key(request: Any) -> str:
        return str(request.headers.get("X-User-Id", "anonymous"))

    with Route.group(middleware=[Throttle(2, key=user_key, store=store)]):

        @Route.get("/ping")
        async def ping() -> dict[str, bool]:
            return {"ok": True}

    del ping  # registered via @Route.get; drop local binding
    app = FastAPI()
    HttpExceptionHandler().register(app)
    Router.singleton().register_with_app(app)
    client = TestClient(app)

    # Two different users share the limiter but with different keys
    for _ in range(2):
        assert client.get("/ping", headers={"X-User-Id": "alice"}).status_code == 200
    for _ in range(2):
        assert client.get("/ping", headers={"X-User-Id": "bob"}).status_code == 200

    # Alice is now throttled
    assert client.get("/ping", headers={"X-User-Id": "alice"}).status_code == 429


def test_redis_store_class_exists() -> None:
    """RedisStore importable; runtime requires arvel[redis] installed.

    We don't run a Redis container in unit tests; just confirm the class is wired.
    """
    from arvel.http.ratelimit import RedisStore

    assert RedisStore is not None


def test_attempt_namedtuple_shape() -> None:
    from arvel.http.ratelimit import Attempt

    a = Attempt(count=3, reset_at=datetime.now(UTC))
    assert a.count == 3
    assert isinstance(a.reset_at, datetime)
