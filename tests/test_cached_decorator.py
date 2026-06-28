"""Cache (doc 16) — @cached memoizes an async function's result in the default cache."""

from __future__ import annotations

from arvel.cache import CacheManager, cached
from arvel.kernel import Application, set_application


def _bind_fresh_cache() -> None:
    app = Application()
    app.instance("cache", CacheManager())  # fresh array cache per test
    set_application(app)


async def test_cached_memoizes_by_args() -> None:
    _bind_fresh_cache()
    calls: list[int] = []

    @cached(ttl=60)
    async def square(n: int) -> int:
        calls.append(n)
        return n * n

    try:
        assert await square(3) == 9
        assert await square(3) == 9  # served from cache
        assert await square(4) == 16  # different arg → fresh compute
        assert calls == [3, 4]  # 3 computed once, 4 once
    finally:
        set_application(None)


async def test_cached_bare_decorator() -> None:
    _bind_fresh_cache()
    calls: list[int] = []

    @cached
    async def load() -> int:
        calls.append(1)
        return 42

    try:
        assert await load() == 42
        assert await load() == 42
        assert calls == [1]  # computed once
    finally:
        set_application(None)


async def test_cached_caches_none_distinct_from_miss() -> None:
    _bind_fresh_cache()
    calls: list[int] = []

    @cached(ttl=60)
    async def maybe() -> None:
        calls.append(1)
        return None

    try:
        assert await maybe() is None
        assert await maybe() is None  # cached None, not recomputed
        assert calls == [1]
    finally:
        set_application(None)


async def test_cached_explicit_key_shared() -> None:
    _bind_fresh_cache()

    @cached(key="fixed", ttl=60)
    async def a() -> str:
        return "from-a"

    @cached(key="fixed", ttl=60)
    async def b() -> str:
        return "from-b"

    try:
        assert await a() == "from-a"
        assert await b() == "from-a"  # same explicit key → b sees a's cached value
    finally:
        set_application(None)
