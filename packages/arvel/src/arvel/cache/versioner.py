"""CacheVersioner — version-stamped cache key invalidation.

Pattern extracted from the kit's ``ItemService``. Instead of deleting
individual cache entries on write, we bump a version counter stored under a
dedicated key. Any subsequent call to :meth:`versioned_key` generates a new
composite key that differs from all pre-invalidation keys, effectively making
the old entries unreachable (they expire naturally via TTL).

Usage::

 versioner = CacheVersioner("items:list", store=cache_store)

 # Build a key for a specific filter set
 key = await versioner.versioned_key("user:1", "page:2")
 cached = await store.get(key)

 # Invalidate all list caches for this prefix
 await versioner.invalidate
 # versioner.versioned_key(...) now returns a different key.

Each ``CacheVersioner`` instance is scoped to a prefix so two versioners
with different prefixes don't interfere (AC-18).
"""

from __future__ import annotations

import uuid

from arvel.cache.store import CacheStore


class CacheVersioner:
    """Version-stamp a family of cache keys under a shared prefix.

    Invalidation is O(1): bump the version, old keys become orphaned.
    """

    def __init__(self, prefix: str, *, store: CacheStore) -> None:
        self._prefix = prefix
        self._store = store
        # Internal key where the current version UUID is stored.
        self._version_key = f"__cache_version::{prefix}"

    async def _current_version(self) -> str:
        version: object = await self._store.get(self._version_key)
        if version is None:
            new_ver = str(uuid.uuid4())
            await self._store.forever(self._version_key, new_ver)
            return new_ver
        return str(version)

    async def versioned_key(self, *parts: str) -> str:
        """Return a cache key that encodes the current version and ``parts``.

        The key changes whenever :meth:`invalidate` is called.
        """
        version = await self._current_version()
        suffix = ":".join(parts)
        return f"{self._prefix}::{version}::{suffix}"

    async def invalidate(self) -> None:
        """Bump the version so all existing versioned keys become stale."""
        new_ver = str(uuid.uuid4())
        await self._store.forever(self._version_key, new_ver)


__all__ = ["CacheVersioner"]
