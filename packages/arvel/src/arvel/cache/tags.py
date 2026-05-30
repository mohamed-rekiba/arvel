"""TaggedCache — namespace-based tag invalidation on top of any CacheStore."""

from __future__ import annotations

import uuid
from typing import Any

from arvel.cache.store import CacheStore


class TaggedCache:
    """Wraps a cache store with tag-scoped operations.

    Namespace rotation approach: each tag maps to a random UUID stored in the
    cache. Flushing a tag rotates its UUID — all prefixed keys become unreachable
    without a full scan. O(1) flush.
    """

    def __init__(self, store: CacheStore, tags: list[str]) -> None:
        self._store = store
        self._tags = tags

    async def _tag_namespace(self, tag: str) -> str:
        ns_key = f"tag_namespace:{tag}"
        ns = await self._store.get(ns_key)
        if ns is None:
            ns = uuid.uuid7().hex
            await self._store.forever(ns_key, ns)
        return str(ns)

    async def _namespace_key(self, key: str) -> str:
        namespaces = [await self._tag_namespace(t) for t in self._tags]
        prefix = "|".join(namespaces)
        return f"tagged:{prefix}:{key}"

    async def put(self, key: str, value: Any, ttl: int | None = None) -> None:
        await self._store.put(await self._namespace_key(key), value, ttl=ttl)

    async def get(self, key: str, default: Any = None) -> Any | None:
        return await self._store.get(await self._namespace_key(key), default)

    async def forget(self, key: str) -> bool:
        return await self._store.forget(await self._namespace_key(key))

    async def flush(self) -> None:
        """Rotate all tag namespaces — makes all tagged keys unreachable."""
        for tag in self._tags:
            new_ns = uuid.uuid7().hex
            await self._store.forever(f"tag_namespace:{tag}", new_ns)


__all__ = ["TaggedCache"]
