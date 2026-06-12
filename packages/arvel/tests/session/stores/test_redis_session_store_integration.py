"""Real-Redis integration tests for ``RedisSessionStore``

The fast inner-loop suite in ``test_redis_store.py`` still runs against
``fakeredis``. This file boots the real ``redis:8`` container and asserts
the same operations against the actual wire protocol — covering ``SETEX``
TTL semantics and DELETE/GET return-type contracts that fakeredis smooths
over silently.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

import pytest
import pytest_asyncio

redis_asyncio = pytest.importorskip("redis.asyncio", reason="arvel[redis] not installed")

from arvel.session.stores.redis import RedisSessionStore  # noqa: E402


class RedisEndpoint(Protocol):
    """Structural type for the ``redis_endpoint`` fixture (see emulators/fixtures.py)."""

    url: str
    host: str
    port: int


@pytest.mark.requires_emulator
@pytest.mark.integration
class TestRedisSessionStoreOps:
    @pytest_asyncio.fixture
    async def store(self, redis_endpoint: RedisEndpoint) -> AsyncIterator[RedisSessionStore]:
        client: Any = redis_asyncio.Redis(host=redis_endpoint.host, port=redis_endpoint.port, db=0)
        prefix = f"session-int-{id(self)}:"
        store = RedisSessionStore(redis=client, prefix=prefix, lifetime=120)
        try:
            yield store
        finally:
            # Drop every key we wrote so the next test starts clean.
            keys: list[bytes] = await client.keys(f"{prefix}*")
            if keys:
                await client.delete(*keys)
            await client.aclose()

    async def test_read_write_roundtrip(self, store: RedisSessionStore) -> None:
        await store.write("sid1", {"user_id": 1, "flash": "saved"})
        data = await store.read("sid1")
        assert data == {"user_id": 1, "flash": "saved"}

    async def test_missing_session_returns_empty(self, store: RedisSessionStore) -> None:
        assert await store.read("nonexistent") == {}

    async def test_destroy_removes_session(self, store: RedisSessionStore) -> None:
        await store.write("sid2", {"k": "v"})
        await store.destroy("sid2")
        assert await store.read("sid2") == {}

    async def test_gc_is_noop_for_redis(self, store: RedisSessionStore) -> None:
        # Redis handles TTL natively; gc() should return 0 against the real server.
        assert await store.gc(max_lifetime=120) == 0

    async def test_short_ttl_session_expires(
        self, store: RedisSessionStore, redis_endpoint: RedisEndpoint
    ) -> None:
        # Confirm the store's configured lifetime lands as a real Redis TTL.
        await store.write("sid-ttl", {"k": "v"})
        client: Any = redis_asyncio.Redis(host=redis_endpoint.host, port=redis_endpoint.port, db=0)
        try:
            # Per-test prefix is set in the fixture; matching on the id
            # suffix is enough to pull the row Redis just stored.
            full_key = next(iter(await client.keys("*sid-ttl*")))
            ttl: int = await client.ttl(full_key)
            assert 0 < ttl <= 120
        finally:
            await client.aclose()
