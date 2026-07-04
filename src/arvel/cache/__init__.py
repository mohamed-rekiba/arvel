"""arvel.cache — the Cache manager on **cashews** (mandated engine; DR-0002).

``array`` (in-memory) is the core driver; ``redis`` needs the ``[redis]`` extra —
both are real cashews backends (never a stdlib stand-in: G4). The ``CacheRepository``
wraps a ``cashews.Cache`` with Laravel-style ``get``/``put``/``remember``/``forget``/
``add``/``pull``/``forever``/``touch``/``increment``/``decrement``/``flexible`` verbs,
an owner-tokened atomic ``CacheLock`` (``lock``/``restore_lock``), and tag-scoped
``tags(...)`` -> ``TaggedCache``. cashews is imported lazily so ``import arvel`` stays
light. Grounded in knowledge/port/16-managers.md.
"""

from __future__ import annotations

import asyncio
import inspect
import secrets
import time
from collections.abc import Callable
from typing import Any

from arvel.kernel import Settings
from arvel.support.manager import Manager
from arvel.telemetry import span

# Compare-and-delete: only unlocks when the stored value still matches this holder's owner
# token — a plain GET-then-DEL would race across processes, so redis needs the two folded
# into one atomic script (the array driver needs no such thing: no `await` sits between its
# check and its delete, so nothing else can interleave — see `_ArrayLockStore`).
_LOCK_RELEASE_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
"""


class CacheSettings(Settings):
    """Typed, validated view over the ``cache`` config section (DR-0016).

    ``default`` is a driver name (an open registry — packages add drivers — so it stays ``str``);
    ``url`` is the redis DSN for the ``redis`` driver.
    """

    __config_key__ = "cache"
    default: str = "array"
    url: str = "redis://localhost:6379/0"


class LockTimeout(RuntimeError):
    """Raised by :meth:`CacheLock.block` when the wait elapses without acquiring (Laravel's
    ``LockTimeoutException``)."""


class LockAcquireFailed(RuntimeError):
    """Raised by ``async with lock:`` when the lock isn't acquired on the first try. The
    context-manager form never silently blocks — use :meth:`CacheLock.block` for that
    (explicit beats implicit)."""


class TagsUnsupported(RuntimeError):
    """Raised when tags are requested against a store that can't provide them. Both drivers here
    (array, redis) support tags; this guards a future non-taggable store."""


class _ArrayLockStore:
    """Process-wide lock table for the array driver — an asyncio-safe plain dict.

    Every method here is synchronous (no ``await`` anywhere in the body), so a whole
    acquire-check-and-set or release-check-and-delete runs without the event loop ever getting a
    chance to interleave another task in the middle — atomic for free, no extra locking needed.
    """

    def __init__(self) -> None:
        self._locks: dict[str, tuple[str, float | None]] = {}

    def _live(self, name: str) -> tuple[str, float | None] | None:
        current = self._locks.get(name)
        if current is None:
            return None
        _, expires_at = current
        if expires_at is not None and expires_at <= time.monotonic():
            del self._locks[name]
            return None
        return current

    def try_acquire(self, name: str, owner: str, seconds: int | None) -> bool:
        if self._live(name) is not None:
            return False
        expires_at = time.monotonic() + seconds if seconds is not None else None
        self._locks[name] = (owner, expires_at)
        return True

    def release(self, name: str, owner: str) -> bool:
        current = self._live(name)
        if current is None or current[0] != owner:
            return False
        del self._locks[name]
        return True

    def force_release(self, name: str) -> None:
        self._locks.pop(name, None)


class CacheLock:
    """An atomic, owner-tokened lock (Laravel ``Cache::lock``).

    Only the holder that acquired it (or a handle restored with its exact owner token, via
    :meth:`CacheRepository.restore_lock`) can :meth:`release` it; :meth:`force_release` is
    unconditional. ``async with lock:`` tries once and raises :class:`LockAcquireFailed` if the
    lock is already held; use :meth:`block` to wait.
    """

    def __init__(
        self,
        repository: CacheRepository,
        name: str,
        seconds: int | None = None,
        owner: str | None = None,
    ) -> None:
        self._repository = repository
        self._name = name
        self._seconds = seconds
        self._owner = owner or secrets.token_hex(16)

    def owner(self) -> str:
        """This handle's owner token (random per-instance unless restored)."""
        return self._owner

    async def acquire(self) -> bool:
        attrs = {"cache.operation": "lock.acquire", "cache.lock": self._name}
        with span("cache lock acquire", kind="client", attributes=attrs):
            return await self._repository._lock_acquire(  # pyright: ignore[reportPrivateUsage]
                self._name, self._owner, self._seconds
            )

    async def block(self, wait_seconds: float, sleep: float = 0.25) -> None:
        """Retry until acquired, or raise :class:`LockTimeout` once ``wait_seconds`` elapses."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_seconds
        while True:
            if await self.acquire():
                return
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise LockTimeout(
                    f"Timed out after {wait_seconds}s waiting for lock {self._name!r}"
                )
            await asyncio.sleep(min(sleep, remaining))

    async def release(self) -> bool:
        """Delete the lock only if this handle's owner token still holds it."""
        attrs = {"cache.operation": "lock.release", "cache.lock": self._name}
        with span("cache lock release", kind="client", attributes=attrs):
            return await self._repository._lock_release(  # pyright: ignore[reportPrivateUsage]
                self._name, self._owner
            )

    async def force_release(self) -> None:
        """Delete the lock unconditionally, regardless of owner."""
        attrs = {"cache.operation": "lock.force_release", "cache.lock": self._name}
        with span("cache lock force_release", kind="client", attributes=attrs):
            await self._repository._lock_force_release(  # pyright: ignore[reportPrivateUsage]
                self._name
            )

    async def __aenter__(self) -> CacheLock:
        if not await self.acquire():
            raise LockAcquireFailed(f"Lock {self._name!r} is already held")
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.release()


class TaggedCache:
    """A repository scoped to one or more tags (Laravel ``Cache::tags(...)``).

    Entries are keyed by the exact (sorted) tag combination, so they're readable only through
    that same combination — a plain ``repository.get(key)`` or a different tag set never sees
    them. ``flush()`` deletes every entry ever written under **any** of these tags, even via a
    different combination, mirroring Laravel's cross-combination tag invalidation.
    """

    def __init__(self, repository: CacheRepository, names: tuple[str, ...]) -> None:
        self._repository = repository
        self._names = tuple(sorted(set(names)))

    def _scoped_key(self, key: str) -> str:
        return f"_tag:{'+'.join(self._names)}:{key}"

    def _tagset_key(self, name: str) -> str:
        return f"_tagset:{name}"

    async def _register(self, key: str) -> None:
        scoped = self._scoped_key(key)
        client = self._repository.client
        for name in self._names:
            await client.set_add(self._tagset_key(name), scoped)

    async def get(self, key: str, default: Any = None) -> Any:
        return await self._repository.get(self._scoped_key(key), default)

    async def put(self, key: str, value: Any, ttl: int | None = None) -> bool:
        await self._register(key)
        return await self._repository.put(self._scoped_key(key), value, ttl)

    async def has(self, key: str) -> bool:
        return await self._repository.has(self._scoped_key(key))

    async def forget(self, key: str) -> bool:
        return await self._repository.forget(self._scoped_key(key))

    async def add(self, key: str, value: Any, ttl: int | None = None) -> bool:
        stored = await self._repository.add(self._scoped_key(key), value, ttl)
        if stored:
            await self._register(key)
        return stored

    async def pull(self, key: str, default: Any = None) -> Any:
        return await self._repository.pull(self._scoped_key(key), default)

    async def forever(self, key: str, value: Any) -> bool:
        await self._register(key)
        return await self._repository.forever(self._scoped_key(key), value)

    async def touch(self, key: str, ttl: int) -> bool:
        return await self._repository.touch(self._scoped_key(key), ttl)

    async def expire(self, key: str, ttl: int) -> bool:
        return await self._repository.expire(self._scoped_key(key), ttl)

    async def increment(self, key: str, by: int = 1) -> int:
        await self._register(key)
        return await self._repository.increment(self._scoped_key(key), by)

    async def decrement(self, key: str, by: int = 1) -> int:
        await self._register(key)
        return await self._repository.decrement(self._scoped_key(key), by)

    async def remember(self, key: str, ttl: int | None, callback: Any) -> Any:
        await self._register(key)
        return await self._repository.remember(self._scoped_key(key), ttl, callback)

    async def remember_forever(self, key: str, callback: Any) -> Any:
        return await self.remember(key, None, callback)

    async def flush(self) -> bool:
        """Delete every entry ever written under any of these tags, then clear their member sets."""
        client = self._repository.client
        for name in self._names:
            set_key = self._tagset_key(name)
            while True:
                members = await client.set_pop(set_key, 1000)
                if not members:
                    break
                for member in members:
                    await client.delete(member)
        return True


class CacheRepository:
    """Laravel-style cache API over a configured ``cashews.Cache`` client."""

    def __init__(self, client: Any, *, driver: str = "array") -> None:
        self._client = client
        self._driver = driver
        self._array_lock_store: _ArrayLockStore | None = None
        # Kept alive so `flexible()`'s fire-and-forget revalidation isn't garbage-collected
        # mid-flight (asyncio only guarantees a task runs while something holds a reference).
        self._background_tasks: set[asyncio.Task[None]] = set()

    @property
    def client(self) -> Any:
        return self._client

    async def get(self, key: str, default: Any = None) -> Any:
        with span("cache get", kind="client", attributes={"cache.operation": "get"}) as sp:
            value = await self._client.get(key)
            if sp is not None:
                sp.set_attribute("cache.hit", value is not None)
            return default if value is None else value

    async def put(self, key: str, value: Any, ttl: int | None = None) -> bool:
        with span("cache put", kind="client", attributes={"cache.operation": "put"}):
            await self._client.set(key, value, expire=ttl)
            return True

    async def has(self, key: str) -> bool:
        return await self._client.get(key) is not None

    async def forget(self, key: str) -> bool:
        with span("cache forget", kind="client", attributes={"cache.operation": "forget"}):
            await self._client.delete(key)
            return True

    async def flush(self) -> bool:
        """Remove every entry from the store (Laravel ``Cache::flush`` / ``cache:clear``)."""
        with span("cache flush", kind="client", attributes={"cache.operation": "flush"}):
            await self._client.clear()
            return True

    async def add(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Set-if-absent (Laravel ``Cache::add``) — a single atomic SET NX on redis (cashews
        ``set(..., exist=False)``); ``True`` only when this call actually stored the value."""
        with span("cache add", kind="client", attributes={"cache.operation": "add"}) as sp:
            stored = bool(await self._client.set(key, value, expire=ttl, exist=False))
            if sp is not None:
                sp.set_attribute("cache.stored", stored)
            return stored

    async def pull(self, key: str, default: Any = None) -> Any:
        """Get then delete in one call (Laravel ``Cache::pull``)."""
        with span("cache pull", kind="client", attributes={"cache.operation": "pull"}) as sp:
            value = await self._client.get(key)
            if value is None:
                return default
            await self._client.delete(key)
            if sp is not None:
                sp.set_attribute("cache.hit", True)
            return value

    async def forever(self, key: str, value: Any) -> bool:
        """Store with no expiry (Laravel ``Cache::forever``)."""
        return await self.put(key, value, ttl=None)

    async def touch(self, key: str, ttl: int) -> bool:
        """Refresh a key's TTL (Laravel ``Cache::touch`` — the Laravel-named alias of :meth:`expire`)."""
        with span("cache touch", kind="client", attributes={"cache.operation": "touch"}):
            return await self.expire(key, ttl)

    async def increment(self, key: str, by: int = 1) -> int:
        """Atomically add ``by`` to a counter (created at 0 if absent); returns the new value."""
        with span("cache increment", kind="client", attributes={"cache.operation": "increment"}):
            return int(await self._client.incr(key, by))

    async def decrement(self, key: str, by: int = 1) -> int:
        """Atomically subtract ``by`` from a counter; returns the new value (mirrors :meth:`increment`)."""
        with span("cache decrement", kind="client", attributes={"cache.operation": "decrement"}):
            return int(await self._client.incr(key, -by))

    async def expire(self, key: str, ttl: int) -> bool:
        """Set/refresh a key's time-to-live in seconds."""
        await self._client.expire(key, ttl)
        return True

    async def remember(self, key: str, ttl: int | None, callback: Any) -> Any:
        value = await self._client.get(key)
        if value is not None:
            return value
        computed = callback()
        if inspect.isawaitable(computed):
            computed = await computed
        await self._client.set(key, computed, expire=ttl)
        return computed

    async def remember_forever(self, key: str, callback: Any) -> Any:
        return await self.remember(key, None, callback)

    async def flexible(
        self,
        key: str,
        fresh_stale: tuple[int, int],
        callback: Any,
        *,
        clock: Callable[[], float] = time.time,
    ) -> Any:
        """Stale-while-revalidate (Laravel ``Cache::flexible``).

        Stores ``(value, stored_at)``. Within ``fresh`` seconds of ``stored_at``, serves the
        cached value. Past ``fresh`` but within ``stale``, serves the (stale) cached value and
        fires a background revalidation — single-flight, guarded by :meth:`add` so concurrent
        stale hits refresh only once. Past ``stale`` (or on a miss), recomputes inline. ``clock``
        is injectable so tests can control "now" without real sleeps.
        """
        fresh, stale = fresh_stale
        attrs = {"cache.operation": "flexible"}
        with span("cache flexible", kind="client", attributes=attrs) as sp:
            entry = await self._client.get(key)
            now = clock()
            if entry is not None:
                value, stored_at = entry
                age = now - stored_at
                if age <= fresh:
                    if sp is not None:
                        sp.set_attribute("cache.flexible_state", "fresh")
                    return value
                if age <= stale:
                    if sp is not None:
                        sp.set_attribute("cache.flexible_state", "stale")
                    await self._revalidate_once(key, stale, callback, clock)
                    return value
            if sp is not None:
                sp.set_attribute("cache.flexible_state", "miss" if entry is None else "expired")
            computed = callback()
            if inspect.isawaitable(computed):
                computed = await computed
            await self._client.set(key, (computed, now), expire=stale)
            return computed

    async def _revalidate_once(
        self, key: str, stale: int, callback: Any, clock: Callable[[], float]
    ) -> None:
        """Fire a background recompute for ``key``, guarded so only one caller per stale window
        actually revalidates (the rest just serve the stale value they already have)."""
        guard_key = f"_flexible_revalidating:{key}"
        if not await self.add(guard_key, "1", ttl=max(stale, 1)):
            return

        async def _run() -> None:
            try:
                computed = callback()
                if inspect.isawaitable(computed):
                    computed = await computed
                await self._client.set(key, (computed, clock()), expire=stale)
            finally:
                await self._client.delete(guard_key)

        task = asyncio.create_task(_run())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def wait_for_pending_revalidations(self) -> None:
        """Await any in-flight :meth:`flexible` background revalidations — a test/shutdown seam
        so callers don't have to guess at sleep durations for a fire-and-forget task."""
        tasks = list(self._background_tasks)
        if tasks:
            await asyncio.gather(*tasks)

    # --- locks ---------------------------------------------------------------
    def lock(self, name: str, seconds: int | None = None, owner: str | None = None) -> CacheLock:
        """An atomic, owner-tokened lock (Laravel ``Cache::lock``)."""
        return CacheLock(self, name, seconds, owner)

    def restore_lock(self, name: str, owner: str) -> CacheLock:
        """Recreate a lock handle for a stored owner token (Laravel ``Cache::restoreLock``) — lets
        a different process/instance than the one that acquired the lock release it."""
        return CacheLock(self, name, owner=owner)

    async def _redis_raw_client(self, key: str) -> Any:
        """Reach the cashews-managed redis backend's raw ``redis.asyncio`` client.

        cashews exposes no public accessor for it, so this pulls it off the backend directly
        (the same backend cashews already created and pools — never a second connection). Mirrors
        cashews' own lazy-init middleware: initializes the backend on first use if needed.
        """
        backend = self._client._get_backend(key)
        if not backend.is_init:
            await backend.init()
        return backend._client

    def _array_locks(self) -> _ArrayLockStore:
        if self._array_lock_store is None:
            self._array_lock_store = _ArrayLockStore()
        return self._array_lock_store

    async def _lock_acquire(self, name: str, owner: str, seconds: int | None) -> bool:
        if self._driver == "redis":
            client = await self._redis_raw_client(name)
            px = int(seconds * 1000) if seconds is not None else None
            return bool(await client.set(name, owner, nx=True, px=px))
        return self._array_locks().try_acquire(name, owner, seconds)

    async def _lock_release(self, name: str, owner: str) -> bool:
        if self._driver == "redis":
            client = await self._redis_raw_client(name)
            result = await client.eval(_LOCK_RELEASE_SCRIPT, 1, name, owner)
            return bool(result)
        return self._array_locks().release(name, owner)

    async def _lock_force_release(self, name: str) -> None:
        if self._driver == "redis":
            client = await self._redis_raw_client(name)
            await client.delete(name)
            return
        self._array_locks().force_release(name)

    # --- tags ------------------------------------------------------------------
    def tags(self, *names: str) -> TaggedCache:
        """Scope this repository to the given tags (Laravel ``Cache::tags(...)``)."""
        if not names:
            raise ValueError("tags() requires at least one tag name")
        return TaggedCache(self, names)


class CacheManager(Manager):
    """Resolves cache drivers (cashews backends) by config."""

    def default_driver(self) -> str:
        return self._settings(CacheSettings).default  # auto-loads + validates config("cache")

    def _build(self, url: str, *, driver: str, **backend_options: Any) -> CacheRepository:
        from cashews import Cache

        client = Cache()
        client.setup(url, **backend_options)
        return CacheRepository(client, driver=driver)

    def create_array_driver(self) -> CacheRepository:
        return self._build("mem://", driver="array")

    def create_redis_driver(self) -> CacheRepository:
        # cashews defaults suppress=True (a dead Redis silently no-ops); we need it to raise,
        # or cache-dependent correctness (locks, throttles) degrades silently.
        return self._build(self._settings(CacheSettings).url, driver="redis", suppress=False)


_CACHE_MISS: Any = object()


def cached(fn: Any = None, *, ttl: int | None = None, key: str | None = None) -> Any:
    """Memoize an **async** function's result in the default cache. Use bare (``@cached``) or with
    options (``@cached(ttl=300)``). The key defaults to the qualified name + the call's args; pass
    ``key=`` to fix it. A stored ``None`` is cached correctly (distinguished from a miss)."""
    if fn is None:

        def _decorate(f: Any) -> Any:
            return cached(f, ttl=ttl, key=key)

        return _decorate

    import functools

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        from arvel.support import cache

        cache_key = key or f"{fn.__module__}.{fn.__qualname__}:{args!r}:{sorted(kwargs.items())!r}"
        repo = cache()
        # Wrap in a 1-tuple so a cached None is never confused with a miss.
        hit = await repo.get(cache_key, _CACHE_MISS)
        if hit is not _CACHE_MISS:
            return hit[0]
        result = await fn(*args, **kwargs)
        await repo.put(cache_key, (result,), ttl=ttl)
        return result

    return wrapper


__all__ = [
    "CacheLock",
    "CacheManager",
    "CacheRepository",
    "CacheSettings",
    "LockAcquireFailed",
    "LockTimeout",
    "TaggedCache",
    "TagsUnsupported",
    "cached",
]
