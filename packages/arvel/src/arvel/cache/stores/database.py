"""DatabaseStore — SQLAlchemy-backed cache using a ``cache_entries`` table."""

from __future__ import annotations

import json
import random
import time
from typing import Any, cast

from sqlalchemy import Integer, String, Text, delete
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class _CacheBase(DeclarativeBase):
    pass


class CacheEntry(_CacheBase):
    """ORM table backing :class:`DatabaseStore` (``cache_entries``)."""

    __tablename__ = "cache_entries"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False)


class DatabaseStore:
    """Cache store backed by a ``cache_entries`` SQL table.

    Call ``await create_table(engine)`` once (or via migration) before first use.
    """

    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        prefix: str = "arvel_cache",
        gc_probability: int = 2,
    ) -> None:
        self.session_maker = session_maker
        self._prefix = prefix
        self._gc_probability = gc_probability

    async def create_table(self, engine: AsyncEngine) -> None:
        """Create the cache_entries table if it doesn't exist."""
        async with engine.begin() as conn:
            await conn.run_sync(_CacheBase.metadata.create_all)

    def _key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    async def _maybe_gc(self) -> None:
        # Probabilistic GC sampling, not cryptographic randomness.
        if self._gc_probability > 0 and random.randint(1, 100) <= self._gc_probability:  # nosec B311
            await self.gc()

    async def put(self, key: str, value: Any, ttl: int | None = None) -> None:
        expires_at = 0 if ttl is None else int(time.time()) + ttl
        full_key = self._key(key)
        serialized = json.dumps(value)
        async with self.session_maker() as session, session.begin():
            existing = await session.get(CacheEntry, full_key)
            if existing:
                existing.value = serialized
                existing.expires_at = expires_at
            else:
                session.add(CacheEntry(key=full_key, value=serialized, expires_at=expires_at))

    async def get(self, key: str, default: Any = None) -> Any | None:
        await self._maybe_gc()
        full_key = self._key(key)
        async with self.session_maker() as session:
            entry = await session.get(CacheEntry, full_key)
            if entry is None:
                return default
            if entry.expires_at != 0 and int(time.time()) > entry.expires_at:
                async with session.begin():
                    await session.delete(entry)
                return default
            return json.loads(entry.value)

    async def forget(self, key: str) -> bool:
        full_key = self._key(key)
        async with self.session_maker() as session, session.begin():
            entry = await session.get(CacheEntry, full_key)
            if entry:
                await session.delete(entry)
                return True
        return False

    async def has(self, key: str) -> bool:
        full_key = self._key(key)
        async with self.session_maker() as session:
            entry = await session.get(CacheEntry, full_key)
            if entry is None:
                return False
            if entry.expires_at != 0 and int(time.time()) > entry.expires_at:
                async with session.begin():
                    await session.delete(entry)
                return False
            return True

    async def flush(self) -> None:
        async with self.session_maker() as session, session.begin():
            await session.execute(delete(CacheEntry))

    async def forever(self, key: str, value: Any) -> None:
        await self.put(key, value, ttl=None)

    async def many(self, keys: list[str]) -> dict[str, Any | None]:
        return {k: await self.get(k) for k in keys}

    async def put_many(self, values: dict[str, Any], ttl: int | None = None) -> None:
        for k, v in values.items():
            await self.put(k, v, ttl=ttl)

    async def gc(self, max_lifetime: int = 3600) -> int:
        now = int(time.time())
        async with self.session_maker() as session, session.begin():
            result = cast(
                "CursorResult[Any]",
                await session.execute(
                    delete(CacheEntry).where(
                        CacheEntry.expires_at != 0, CacheEntry.expires_at < now
                    )
                ),
            )
            return int(result.rowcount)


__all__ = ["CacheEntry", "DatabaseStore"]
