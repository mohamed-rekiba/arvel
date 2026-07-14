"""arvel.cache — the Cache manager on **cashews** (mandated engine; DR-0002).

``array`` (in-memory) is the core driver; ``redis`` needs the ``[redis]`` extra —
both are real cashews backends (never a stdlib stand-in: G4). The ``CacheRepository``
wraps a ``cashews.Cache`` with ``get``/``put``/``remember``/``forget``/
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
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

import msgspec

from arvel.kernel import Settings
from arvel.support.manager import Manager, MissingExtraError
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

# Same compare-then-act shape as the release script above, but extends the TTL instead of
# deleting — still only when this holder's owner token still holds it.
_LOCK_REFRESH_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("PEXPIRE", KEYS[1], ARGV[2])
else
    return 0
end
"""


@dataclass(frozen=True)
class CacheHit:
    """Dispatched when a read finds a stored value (a stored ``None`` counts as a hit)."""

    key: str
    value: Any


@dataclass(frozen=True)
class CacheMissed:
    """Dispatched when a read finds nothing stored for ``key``."""

    key: str


@dataclass(frozen=True)
class KeyWritten:
    """Dispatched after a value is stored."""

    key: str
    value: Any
    ttl: int | None = None


@dataclass(frozen=True)
class KeyForgotten:
    """Dispatched after a key is deleted."""

    key: str


async def _dispatch_cache_event(event: Any) -> None:
    """Best-effort dispatch through the app's event bus; a no-op without one (mirrors
    ``arvel.auth._dispatch_auth_event`` / database's ``QueryExecuted`` dispatch)."""
    from arvel.kernel import app, has_application

    if has_application() and app().bound("events"):
        try:
            await app().make("events").dispatch(event)
        except Exception:
            # best-effort means a broken listener can't fail the operation that fired it
            from arvel.kernel.logging import LogManager

            LogManager().channel("cache").warning("event_listener_failed", exc_info=True)


def _wrap(value: Any) -> tuple[Any]:
    """arvel's own envelope for a stored value — a 1-tuple, so a cached ``None`` is stored as
    ``(None,)`` and is never confused with "nothing stored" (a bare ``None`` from the client)."""
    return (value,)


def _unwrap(raw: Any) -> Any:
    """Inverse of :func:`_wrap`. A value written by another (non-arvel) client is passed through
    unchanged, best-effort — this only recognizes this exact 1-tuple shape as arvel's envelope."""
    if isinstance(raw, tuple):
        envelope: tuple[Any, ...] = cast("tuple[Any, ...]", raw)
        if len(envelope) == 1:
            return envelope[0]
    return cast("Any", raw)


class CacheDriver(StrEnum):
    """The built-in cache backends — a typed set for ``cache.default`` / ``stores.<name>.driver``.

    A ``StrEnum`` (not a ``Literal``): ``CacheDriver.REDIS == "redis"`` flows through the string-keyed
    driver dispatch, so config gets type-safety while a plain ``str`` still works for a custom driver
    an ecosystem package registers via ``CacheManager.extend`` — the registry stays open."""

    ARRAY = "array"
    REDIS = "redis"


def _no_stores() -> dict[str, dict[str, Any]]:
    return {}


class CacheSettings(Settings):
    """Typed, validated view over the ``cache`` config section (DR-0016).

    ``default`` is a driver name (an open registry — packages add drivers — so it stays ``str``);
    ``url`` is the redis DSN for the ``redis`` driver.
    """

    __config_key__ = "cache"
    default: str = "array"
    url: str = "redis://localhost:6379/0"
    #: Optional named stores → per-store config (``{"driver": ..., "url": ...}``), so two redis
    #: stores (sessions, throttle) or a renamed store can coexist. A store's ``driver`` selects the
    #: backend; absent, the store name is the driver (back-compat with the driver==name convention).
    stores: dict[str, dict[str, Any]] = msgspec.field(default_factory=_no_stores)


class LockTimeout(RuntimeError):
    """Raised by:meth:`CacheLock.block` when the wait elapses without acquiring ('s
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

    def refresh(self, name: str, owner: str, seconds: int) -> bool:
        current = self._live(name)
        if current is None or current[0] != owner:
            return False
        self._locks[name] = (owner, time.monotonic() + seconds)
        return True

    def force_release(self, name: str) -> None:
        self._locks.pop(name, None)


class CacheLock:
    """An atomic, owner-tokened lock.

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

    async def block(
        self, wait_seconds: float, sleep: float = 0.25, callback: Callable[[], Any] | None = None
    ) -> Any:
        """Retry until acquired, or raise :class:`LockTimeout` once ``wait_seconds`` elapses.

        With ``callback``, once acquired it runs (sync or async) and the lock is released
        afterward — always, even on exception (mirrors :meth:`get`) — and its result is returned.
        Without one, returns ``None`` once acquired and leaves release to the caller (the
        original behaviour)."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_seconds
        while True:
            if await self.acquire():
                return await self._run_and_release(callback) if callback is not None else None
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise LockTimeout(
                    f"Timed out after {wait_seconds}s waiting for lock {self._name!r}"
                )
            await asyncio.sleep(min(sleep, remaining))

    async def get(self, callback: Callable[[], Any]) -> Any:
        """Acquire (single try), run ``callback`` (sync or async), always release — even on
        exception. Raises :class:`LockAcquireFailed` if the lock is already held."""
        if not await self.acquire():
            raise LockAcquireFailed(f"Lock {self._name!r} is already held")
        return await self._run_and_release(callback)

    async def _run_and_release(self, callback: Callable[[], Any]) -> Any:
        try:
            result = callback()
            if inspect.isawaitable(result):
                result = await result
            return result
        finally:
            await self.release()

    async def refresh(self, ttl: int) -> bool:
        """Extend this lock's expiry to ``ttl`` seconds from now — atomic, and only if this
        handle's owner token still holds it (mirrors :meth:`release`'s compare-and-act)."""
        attrs = {"cache.operation": "lock.refresh", "cache.lock": self._name}
        with span("cache lock refresh", kind="client", attributes=attrs):
            return await self._repository._lock_refresh(  # pyright: ignore[reportPrivateUsage]
                self._name, self._owner, ttl
            )

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
    """A repository scoped to one or more tags.

    Entries are keyed by the exact (sorted) tag combination, so they're readable only through
    that same combination — a plain ``repository.get(key)`` or a different tag set never sees
    them. ``flush()`` deletes every entry ever written under **any** of these tags, even via a
    different combination, mirroring the cross-combination tag invalidation.

    ``forget()`` removes an entry's tag membership as it deletes it; :meth:`prune` reclaims the
    members of entries that expired or were evicted (TTL churn), so a long-lived tag's member set
    stays bounded without a full ``flush()``.
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
        scoped = self._scoped_key(key)
        client = self._repository.client
        for name in self._names:
            await client.set_remove(self._tagset_key(name), scoped)  # don't leak a dead member
        return await self._repository.forget(scoped)

    async def prune(self) -> int:
        """Drop tag-set members whose entry has expired or been evicted, so a long-lived tag that
        churns short-TTL keys doesn't grow its member set unbounded between flushes. Returns the
        number of dead members reclaimed.

        ponytail: drains then re-adds survivors (cashews has no non-destructive set read), so a
        write racing the prune could be dropped and re-registered on its next access — self-healing.
        """
        client = self._repository.client
        removed = 0
        for name in self._names:
            set_key = self._tagset_key(name)
            survivors: list[str] = []
            while True:
                members = list(await client.set_pop(set_key, 1000))
                if not members:
                    break
                for member in members:
                    if await self._repository.has(member):
                        survivors.append(member)
                    else:
                        removed += 1
            if survivors:
                await client.set_add(set_key, *survivors)
        return removed

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
    """cache API over a configured ``cashews.Cache`` client."""

    def __init__(self, client: Any, *, driver: str = "array", redis_url: str | None = None) -> None:
        self._client = client
        self._driver = driver
        self._redis_url = redis_url  # for the redis driver's own atomic-lock client
        self._lock_client: Any = None  # lazily built redis.asyncio client, dedicated to locks
        self._array_lock_store: _ArrayLockStore | None = None
        # Kept alive so `flexible()`'s fire-and-forget revalidation isn't garbage-collected
        # mid-flight (asyncio only guarantees a task runs while something holds a reference).
        self._background_tasks: set[asyncio.Task[None]] = set()

    @property
    def client(self) -> Any:
        return self._client

    async def get(self, key: str, default: Any = None) -> Any:
        """A stored ``None`` is a hit — returned as ``None``, not ``default`` (values are kept
        in arvel's own envelope, see :func:`_wrap`, so a stored ``None`` is distinguishable from
        nothing-stored)."""
        with span("cache get", kind="client", attributes={"cache.operation": "get"}) as sp:
            raw = await self._client.get(key)
            hit = raw is not None
            if sp is not None:
                sp.set_attribute("cache.hit", hit)
            if not hit:
                await _dispatch_cache_event(CacheMissed(key))
                return default
            value = _unwrap(raw)
            await _dispatch_cache_event(CacheHit(key, value))
            return value

    async def put(self, key: str, value: Any, ttl: int | None = None) -> bool:
        with span("cache put", kind="client", attributes={"cache.operation": "put"}):
            if ttl is not None and ttl <= 0:
                # a non-positive TTL means "already expired" — evict any existing value, store
                # nothing (cashews reads expire=0 as no-expiry, which would persist it forever).
                await self._client.delete(key)
                await _dispatch_cache_event(KeyForgotten(key))
                return False
            await self._client.set(key, _wrap(value), expire=ttl)
            await _dispatch_cache_event(KeyWritten(key, value, ttl))
            return True

    async def has(self, key: str) -> bool:
        # existence, not truthiness — a key holding None is still present
        return bool(await self._client.exists(key))

    async def forget(self, key: str) -> bool:
        with span("cache forget", kind="client", attributes={"cache.operation": "forget"}):
            await self._client.delete(key)
            await _dispatch_cache_event(KeyForgotten(key))
            return True

    async def flush(self) -> bool:
        """Remove every entry from the store."""
        with span("cache flush", kind="client", attributes={"cache.operation": "flush"}):
            await self._client.clear()
            return True

    async def add(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Set-if-absent — a single atomic SET NX on redis (cashews
        ``set(..., exist=False)``); ``True`` only when this call actually stored the value."""
        with span("cache add", kind="client", attributes={"cache.operation": "add"}) as sp:
            if ttl is not None and ttl <= 0:
                return False  # already-expired → never stored
            stored = bool(await self._client.set(key, _wrap(value), expire=ttl, exist=False))
            if sp is not None:
                sp.set_attribute("cache.stored", stored)
            if stored:
                await _dispatch_cache_event(KeyWritten(key, value, ttl))
            return stored

    async def pull(self, key: str, default: Any = None) -> Any:
        """Get then delete in one call. A stored ``None`` is pulled (and deleted) like any other
        value, not treated as a miss."""
        with span("cache pull", kind="client", attributes={"cache.operation": "pull"}) as sp:
            raw = await self._client.get(key)
            if raw is None:
                await _dispatch_cache_event(CacheMissed(key))
                return default
            value = _unwrap(raw)
            await self._client.delete(key)
            if sp is not None:
                sp.set_attribute("cache.hit", True)
            await _dispatch_cache_event(CacheHit(key, value))
            await _dispatch_cache_event(KeyForgotten(key))
            return value

    async def forever(self, key: str, value: Any) -> bool:
        """Store with no expiry."""
        return await self.put(key, value, ttl=None)

    async def touch(self, key: str, ttl: int) -> bool:
        """Refresh a key's TTL."""
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

    async def increment_with_ttl(self, key: str, amount: int = 1, ttl: int | None = None) -> int:
        """Atomically bump a counter and arm its TTL on the hit that creates it (fixed-window
        counting — e.g. rate limiting — needs "create with decay" to not race between the two
        calls it'd otherwise take). Safe under concurrent callers: cashews folds this into one
        INCR+EXPIRE Lua script on redis, and the array driver has no `await` between its read and
        write (see `_ArrayLockStore`) — so a decay only arms once, on the count-1 creation."""
        with span(
            "cache increment_with_ttl",
            kind="client",
            attributes={"cache.operation": "increment_with_ttl"},
        ):
            return int(await self._client.incr(key, amount, expire=ttl))

    async def expire(self, key: str, ttl: int) -> bool:
        """Set/refresh a key's time-to-live in seconds."""
        await self._client.expire(key, ttl)
        return True

    async def remember(self, key: str, ttl: int | None, callback: Any) -> Any:
        """Serve the cached value if present — a cached ``None`` counts, and is served without
        recomputing — else compute, store, and return it."""
        raw = await self._client.get(key)
        if raw is not None:
            value = _unwrap(raw)
            await _dispatch_cache_event(CacheHit(key, value))
            return value
        await _dispatch_cache_event(CacheMissed(key))
        computed = callback()
        if inspect.isawaitable(computed):
            computed = await computed
        await self._client.set(key, _wrap(computed), expire=ttl)
        await _dispatch_cache_event(KeyWritten(key, computed, ttl))
        return computed

    async def remember_forever(self, key: str, callback: Any) -> Any:
        return await self.remember(key, None, callback)

    async def many(self, keys: Iterable[str], default: Any = None) -> dict[str, Any]:
        """Batch :meth:`get` — one round trip per backend via cashews' native multi-get."""
        keys = list(keys)
        raws = await self._client.get_many(*keys)
        return {
            key: (default if raw is None else _unwrap(raw))
            for key, raw in zip(keys, raws, strict=True)
        }

    async def put_many(self, mapping: Mapping[str, Any], ttl: int | None = None) -> bool:
        """Batch :meth:`put` — one round trip per backend via cashews' native multi-set."""
        if ttl is not None and ttl <= 0:
            for key in mapping:
                await self._client.delete(key)
            return False
        wrapped = {key: _wrap(value) for key, value in mapping.items()}
        await self._client.set_many(wrapped, expire=ttl)
        return True

    async def flexible(
        self,
        key: str,
        fresh_stale: tuple[int, int],
        callback: Any,
        *,
        clock: Callable[[], float] = time.time,
    ) -> Any:
        """Stale-while-revalidate.

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
            except Exception:
                # a fire-and-forget task's exception would otherwise vanish into asyncio's
                # "never retrieved" warning; surface it so ops can see a failing revalidate
                from arvel.kernel.logging import LogManager

                LogManager().channel("cache").warning(
                    "flexible_revalidation_failed", key=key, exc_info=True
                )
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
        """An atomic, owner-tokened lock."""
        return CacheLock(self, name, seconds, owner)

    def restore_lock(self, name: str, owner: str) -> CacheLock:
        """Recreate a lock handle for a stored owner token — lets
        a different process/instance than the one that acquired the lock release it."""
        return CacheLock(self, name, owner=owner)

    async def _redis_raw_client(self) -> Any:
        """A ``redis.asyncio`` client dedicated to the atomic locks (SET NX PX + Lua owner-release).

        cashews exposes no public accessor for its pooled client, so rather than reach into its
        private backend shape, the lock path owns its own connection from the same configured URL.
        Lazily built and reused; closed in :meth:`close`.
        """
        if self._lock_client is None:
            import redis.asyncio as redis_asyncio

            if self._redis_url is None:
                raise RuntimeError("the redis lock path requires a configured redis url")
            self._lock_client = redis_asyncio.from_url(self._redis_url)
        return self._lock_client

    async def close(self) -> None:
        """Close the dedicated lock connection (if the redis lock path was ever used)."""
        if self._lock_client is not None:
            await self._lock_client.aclose()
            self._lock_client = None

    def _array_locks(self) -> _ArrayLockStore:
        if self._array_lock_store is None:
            self._array_lock_store = _ArrayLockStore()
        return self._array_lock_store

    async def _lock_acquire(self, name: str, owner: str, seconds: int | None) -> bool:
        if self._driver == "redis":
            client = await self._redis_raw_client()
            # redis rejects px=0 ("invalid expire time"); seconds=0 means expire-immediately,
            # so the lock is never actually held — match the array path's behaviour, don't 500
            if seconds == 0:
                return False
            px = int(seconds * 1000) if seconds is not None else None
            return bool(await client.set(name, owner, nx=True, px=px))
        return self._array_locks().try_acquire(name, owner, seconds)

    async def _lock_release(self, name: str, owner: str) -> bool:
        if self._driver == "redis":
            client = await self._redis_raw_client()
            result = await client.eval(_LOCK_RELEASE_SCRIPT, 1, name, owner)
            return bool(result)
        return self._array_locks().release(name, owner)

    async def _lock_refresh(self, name: str, owner: str, seconds: int) -> bool:
        if self._driver == "redis":
            client = await self._redis_raw_client()
            px = int(seconds * 1000)
            result = await client.eval(_LOCK_REFRESH_SCRIPT, 1, name, owner, px)
            return bool(result)
        return self._array_locks().refresh(name, owner, seconds)

    async def _lock_force_release(self, name: str) -> None:
        if self._driver == "redis":
            client = await self._redis_raw_client()
            await client.delete(name)
            return
        self._array_locks().force_release(name)

    # --- tags ------------------------------------------------------------------
    def tags(self, *names: str) -> TaggedCache:
        """Scope this repository to the given tags."""
        if not names:
            raise ValueError("tags() requires at least one tag name")
        return TaggedCache(self, names)


class CacheManager(Manager):
    """Resolves cache drivers (cashews backends) by config."""

    def default_driver(self) -> str:
        return self._settings(CacheSettings).default  # auto-loads + validates config("cache")

    def _make(self, name: str) -> Any:
        # name → driver indirection (mirrors FilesystemManager): a named store selects its backend
        # via `stores.<name>.driver`; absent, the name is the driver (back-compat).
        if name in self._creators:
            return self._creators[name](self.app)
        stores = self._settings(CacheSettings).stores
        driver = stores[name].get("driver", name) if name in stores else name
        creator = getattr(self, f"create_{driver}_driver", None)
        if creator is None:
            raise MissingExtraError(driver)
        return creator(name)

    def _build(self, url: str, *, driver: str, **backend_options: Any) -> CacheRepository:
        from cashews import Cache

        client = Cache()
        client.setup(url, **backend_options)
        return CacheRepository(client, driver=driver, redis_url=url if driver == "redis" else None)

    def create_array_driver(self, store: str | None = None) -> CacheRepository:
        return self._build("mem://", driver="array")

    def create_redis_driver(self, store: str | None = None) -> CacheRepository:
        # cashews defaults suppress=True (a dead Redis silently no-ops); we need it to raise,
        # or cache-dependent correctness (locks, throttles) degrades silently. A named store may
        # carry its own `url` (two redis stores); absent, the top-level `url` applies.
        settings = self._settings(CacheSettings)
        url = settings.stores.get(store, {}).get("url", settings.url) if store else settings.url
        return self._build(url, driver="redis", suppress=False)

    async def close(self) -> None:
        """Close every resolved driver's dedicated lock connection — the app's terminating hook
        calls this so the redis lock client is drained on shutdown, not left to the GC."""
        for repo in self._drivers.values():
            await repo.close()


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

        # WARNING: the auto key uses repr() of the args, so it's only stable for args with a stable
        # repr (str/int/…). An object without a custom __repr__ embeds its memory address, so the
        # key differs per instance AND per process — a distributed cache would never hit. Pass an
        # explicit `key=` when caching over object arguments (e.g. a bound method's `self`).
        cache_key = key or f"{fn.__module__}.{fn.__qualname__}:{args!r}:{sorted(kwargs.items())!r}"
        repo = cache()
        # get() distinguishes a cached None from a miss on its own now (CacheRepository's own
        # envelope, see `_wrap`/`_unwrap`) — no decorator-local workaround needed.
        hit = await repo.get(cache_key, _CACHE_MISS)
        if hit is not _CACHE_MISS:
            return hit
        result = await fn(*args, **kwargs)
        await repo.put(cache_key, result, ttl=ttl)
        return result

    return wrapper


__all__ = [
    "CacheDriver",
    "CacheHit",
    "CacheLock",
    "CacheManager",
    "CacheMissed",
    "CacheRepository",
    "CacheSettings",
    "KeyForgotten",
    "KeyWritten",
    "LockAcquireFailed",
    "LockTimeout",
    "TaggedCache",
    "TagsUnsupported",
    "cached",
]
