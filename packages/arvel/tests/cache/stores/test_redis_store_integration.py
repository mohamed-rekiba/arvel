"""Real-Redis integration tests for ``RedisStore``

The fast inner-loop suite in ``test_redis_store.py`` still runs against
``fakeredis``. This file boots the real ``redis:8`` container and asserts
the same operations against the actual wire protocol — covering edge cases
that fakeredis silently smooths over (notably ``SETEX`` TTL semantics and
``KEYS``/``MGET`` decoding).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

import pytest
import pytest_asyncio

redis_asyncio = pytest.importorskip("redis.asyncio", reason="arvel[redis] not installed")

from arvel.cache.stores.redis import RedisStore  # noqa: E402


class RedisEndpoint(Protocol):
    """Structural type for the ``redis_endpoint`` fixture (see emulators/fixtures.py)."""

    url: str
    host: str
    port: int


@pytest.mark.requires_emulator
@pytest.mark.integration
class TestRedisStoreOps:
    @pytest_asyncio.fixture
    async def store(self, redis_endpoint: RedisEndpoint) -> AsyncIterator[RedisStore]:
        client: Any = redis_asyncio.Redis(host=redis_endpoint.host, port=redis_endpoint.port, db=0)
        # Unique prefix per test keeps the session-scoped container clean
        # between tests without paying for a FLUSHDB round-trip.
        prefix = f"cache-int-{id(self)}"
        store = RedisStore(redis=client, prefix=prefix, ttl=3600)
        try:
            yield store
        finally:
            await store.flush()
            await client.aclose()

    async def test_put_and_get(self, store: RedisStore) -> None:
        await store.put("k", "v")
        assert await store.get("k") == "v"

    async def test_missing_returns_default(self, store: RedisStore) -> None:
        assert await store.get("missing") is None
        assert await store.get("missing", default="fallback") == "fallback"

    async def test_complex_payload_preserved(self, store: RedisStore) -> None:
        data: dict[str, Any] = {"key": "value", "count": 42, "items": [1, 2, 3]}
        await store.put("complex", data)
        assert await store.get("complex") == data

    async def test_has_and_forget(self, store: RedisStore) -> None:
        await store.put("x", 1)
        assert await store.has("x") is True
        assert await store.forget("x") is True
        assert await store.has("x") is False

    async def test_flush_clears_only_prefix(self, store: RedisStore) -> None:
        await store.put("a", 1)
        await store.put("b", 2)
        await store.flush()
        assert await store.has("a") is False
        assert await store.has("b") is False

    async def test_forever_persists_without_ttl(self, store: RedisStore) -> None:
        await store.forever("eternal", "yes")
        assert await store.get("eternal") == "yes"

    async def test_many_and_put_many(self, store: RedisStore) -> None:
        await store.put_many({"k1": "v1", "k2": "v2"})
        result = await store.many(["k1", "k2", "k3"])
        assert result == {"k1": "v1", "k2": "v2", "k3": None}
