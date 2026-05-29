"""WI-arvel-047: Cache Correctness cluster — Stories 14, 15, 16.

Tests are FAILING before the fix and PASSING after.

Story 14 (FR-047-014): Cache locks must be atomic using Redis SET NX EX.
Story 15 (FR-047-015): RedisStore.flush() must use SCAN, not blocking KEYS.
Story 16 (FR-047-016): CacheStore.has() must return True for falsy cached values.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from arvel.cache import CacheManager
from arvel.config.cache_config import CacheConfig, CacheDriver

# ─── Story 16: has() must return True for falsy values ───────────────────────


class TestStory16HasFalsyValues:
    """FR-047-016: has(key) must return True for None, False, 0, '' cached values."""

    # ── ArrayStore (in-memory) ───────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_array_store_has_returns_true_for_cached_none(self) -> None:
        """Currently FAILS: get(None) is not None → False, but should be True."""
        manager = CacheManager(CacheConfig(connection=CacheDriver.ARRAY))
        await manager.put("key_none", None, ttl=60)
        assert await manager.has("key_none") is True

    @pytest.mark.asyncio
    async def test_array_store_has_returns_true_for_cached_false(self) -> None:
        manager = CacheManager(CacheConfig(connection=CacheDriver.ARRAY))
        await manager.put("key_false", False, ttl=60)
        assert await manager.has("key_false") is True

    @pytest.mark.asyncio
    async def test_array_store_has_returns_true_for_cached_zero(self) -> None:
        manager = CacheManager(CacheConfig(connection=CacheDriver.ARRAY))
        await manager.put("key_zero", 0, ttl=60)
        assert await manager.has("key_zero") is True

    @pytest.mark.asyncio
    async def test_array_store_has_returns_true_for_cached_empty_string(self) -> None:
        manager = CacheManager(CacheConfig(connection=CacheDriver.ARRAY))
        await manager.put("key_empty", "", ttl=60)
        assert await manager.has("key_empty") is True

    @pytest.mark.asyncio
    async def test_array_store_has_returns_false_for_absent_key(self) -> None:
        """Truly absent key must still return False."""
        manager = CacheManager(CacheConfig(connection=CacheDriver.ARRAY))
        assert await manager.has("key_absent_xyz_123") is False

    # ── FileStore ────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_file_store_has_returns_true_for_cached_none(self, tmp_path: Path) -> None:
        """Currently FAILS: FileStore.has() uses get() is not None."""
        from arvel.cache.stores.file import FileStore

        store = FileStore(path=tmp_path)
        await store.put("key_none", None)
        assert await store.has("key_none") is True

    @pytest.mark.asyncio
    async def test_file_store_has_returns_true_for_cached_false(self, tmp_path: Path) -> None:
        from arvel.cache.stores.file import FileStore

        store = FileStore(path=tmp_path)
        await store.put("key_false", False)
        assert await store.has("key_false") is True

    # ── DatabaseStore ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_database_store_has_returns_true_for_cached_none(self) -> None:
        """Currently FAILS: DatabaseStore.has() uses get() is not None."""
        from arvel.cache.stores.database import DatabaseStore
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        store = DatabaseStore(session_maker=maker, prefix="test047_none")
        await store.create_table(engine)
        await store.put("key_none", None)
        assert await store.has("key_none") is True
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_database_store_has_returns_true_for_cached_false(self) -> None:
        from arvel.cache.stores.database import DatabaseStore
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        store = DatabaseStore(session_maker=maker, prefix="test047_false")
        await store.create_table(engine)
        await store.put("key_false", False)
        assert await store.has("key_false") is True
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_redis_store_has_returns_true_for_cached_none(self) -> None:
        from typing import cast

        import fakeredis.aioredis as fakeredis
        from arvel.cache.stores.redis import RedisConn, RedisStore

        redis = cast("RedisConn", fakeredis.FakeRedis())
        store = RedisStore(redis=redis, prefix="test_has_none")

        await store.put("key_none", None)

        assert await store.has("key_none") is True

    @pytest.mark.asyncio
    async def test_redis_store_has_returns_true_for_cached_false(self) -> None:
        from typing import cast

        import fakeredis.aioredis as fakeredis
        from arvel.cache.stores.redis import RedisConn, RedisStore

        redis = cast("RedisConn", fakeredis.FakeRedis())
        store = RedisStore(redis=redis, prefix="test_has_false")

        await store.put("key_false", False)

        assert await store.has("key_false") is True


# ─── Story 14: Atomic cache locks ─────────────────────────────────────────────


class TestStory14AtomicLocks:
    """FR-047-014: CacheLock.acquire() must be atomic — two concurrent callers cannot both win."""

    class _AtomicRedis:
        def __init__(self) -> None:
            self.values: dict[str, bytes] = {}
            self.set_calls: list[tuple[str, str | bytes, dict[str, object]]] = []
            self.eval_calls: list[tuple[str, int, tuple[str, ...]]] = []

        async def set(self, name: str, value: str | bytes, **kwargs: object) -> bool:
            self.set_calls.append((name, value, dict(kwargs)))
            if kwargs.get("nx") is True and name in self.values:
                return False
            self.values[name] = value if isinstance(value, bytes) else value.encode()
            return True

        async def setex(self, name: str, time: int, value: str | bytes) -> bool:
            self.values[name] = value if isinstance(value, bytes) else value.encode()
            return True

        async def get(self, name: str) -> bytes | None:
            return self.values.get(name)

        async def delete(self, *names: str) -> int:
            deleted = 0
            for name in names:
                if name in self.values:
                    del self.values[name]
                    deleted += 1
            return deleted

        async def exists(self, *names: str) -> int:
            return sum(1 for name in names if name in self.values)

        async def keys(self, pattern: str) -> list[bytes]:
            return []

        async def mget(self, *keys: str) -> list[bytes | None]:
            return [self.values.get(key) for key in keys]

        async def scan(
            self, cursor: int, match: str | None = None, count: int | None = None
        ) -> tuple[int, list[bytes]]:
            return 0, []

        async def eval(self, script: str, numkeys: int, *keys_and_args: str) -> int:
            self.eval_calls.append((script, numkeys, keys_and_args))
            key, owner = keys_and_args
            if self.values.get(key) == owner.encode():
                del self.values[key]
                return 1
            return 0

    @pytest.mark.asyncio
    async def test_concurrent_acquire_only_one_wins(self) -> None:
        """Two concurrent acquire() calls on the same key must produce exactly one True.

        This test exposes the race in the current non-atomic implementation.
        With ArrayStore, the current implementation may occasionally pass or fail
        depending on scheduling. After the fix (atomic SET NX), it must always pass.
        """
        manager = CacheManager(CacheConfig(connection=CacheDriver.ARRAY))

        # Use many concurrent tasks to maximize the chance of exposing the race
        results: list[bool] = []

        async def _try_acquire() -> None:
            async with manager.lock("exclusive-resource", ttl=60) as acquired:
                results.append(acquired)
                if acquired:
                    # Simulate brief work so other coroutines can interleave
                    await asyncio.sleep(0)

        tasks = [asyncio.create_task(_try_acquire()) for _ in range(10)]
        await asyncio.gather(*tasks)

        # Exactly one must have acquired the lock
        winners = [r for r in results if r]
        assert len(winners) == 1, f"Expected 1 winner, got {len(winners)}: {results}"

    @pytest.mark.asyncio
    async def test_lock_released_on_context_exit(self) -> None:
        """Lock must be releasable by the holder and re-acquirable afterward."""
        manager = CacheManager(CacheConfig(connection=CacheDriver.ARRAY))

        async with manager.lock("reuse-lock", ttl=60) as acquired:
            assert acquired is True

        # After release, the lock must be acquirable again
        async with manager.lock("reuse-lock", ttl=60) as acquired2:
            assert acquired2 is True

    @pytest.mark.asyncio
    async def test_lock_release_does_not_affect_other_holder(self) -> None:
        """Release must be token-checked — only the holder can release."""
        from arvel.cache.locks import CacheLock
        from arvel.cache.stores.array import ArrayStore

        store = ArrayStore()
        lock_a = CacheLock(store, "shared", ttl=60)
        lock_b = CacheLock(store, "shared", ttl=60)

        # lock_a acquires
        assert await lock_a.acquire() is True
        # lock_b cannot acquire
        assert await lock_b.acquire() is False

        # lock_b tries to release — must NOT release lock_a's hold
        await lock_b.release()

        # lock_a's lock must still be held
        assert await lock_b.acquire() is False

    @pytest.mark.asyncio
    async def test_redis_lock_acquire_uses_set_nx_ex(self) -> None:
        from arvel.cache.locks import CacheLock
        from arvel.cache.stores.redis import RedisStore

        redis = self._AtomicRedis()
        store = RedisStore(redis=redis, prefix="locks")
        lock = CacheLock(store, "shared", ttl=60)

        assert await lock.acquire() is True

        name, _value, options = redis.set_calls[0]
        assert name == "locks:lock:shared"
        assert options == {"nx": True, "ex": 60}

    @pytest.mark.asyncio
    async def test_redis_lock_release_uses_lua_token_check(self) -> None:
        from arvel.cache.locks import CacheLock
        from arvel.cache.stores.redis import RedisStore

        redis = self._AtomicRedis()
        store = RedisStore(redis=redis, prefix="locks")
        lock_a = CacheLock(store, "shared", ttl=60)
        lock_b = CacheLock(store, "shared", ttl=60)

        assert await lock_a.acquire() is True
        assert await lock_b.acquire() is False

        await lock_b.release()
        assert "locks:lock:shared" in redis.values

        await lock_a.release()
        assert "locks:lock:shared" not in redis.values
        assert redis.eval_calls
        assert 'redis.call("GET", KEYS[1])' in redis.eval_calls[0][0]


# ─── Story 15: Redis flush must use SCAN ──────────────────────────────────────


class TestStory15RedisScanFlush:
    """FR-047-015: RedisStore.flush() must use SCAN instead of blocking KEYS."""

    @pytest.mark.asyncio
    async def test_redis_flush_does_not_use_keys_command(self) -> None:
        """RedisStore.flush() source must use SCAN cursor loop, not KEYS.

        Currently FAILS: implementation uses self._redis.keys(...) directly.
        """
        import inspect

        from arvel.cache.stores.redis import RedisStore

        source = inspect.getsource(RedisStore.flush)
        # After fix: must use scan/scan_iter pattern, NOT keys()
        assert ".keys(" not in source, (
            "RedisStore.flush() must use SCAN iteration, not blocking KEYS command. "
            f"Current implementation: {source!r}"
        )
        # Must use scan or scan_iter
        assert "scan" in source.lower() or "scan_iter" in source.lower()

    @pytest.mark.asyncio
    async def test_redis_flush_clears_all_prefixed_keys(self) -> None:
        """After flush(), all cache keys in the namespace must be gone."""
        from typing import cast

        import fakeredis.aioredis as fakeredis
        from arvel.cache.stores.redis import RedisConn, RedisStore

        redis = cast("RedisConn", fakeredis.FakeRedis())
        store = RedisStore(redis=redis, prefix="test_flush")

        await store.put("alpha", 1)
        await store.put("beta", 2)
        assert await store.has("alpha") is True

        await store.flush()

        assert await store.has("alpha") is False
        assert await store.has("beta") is False
