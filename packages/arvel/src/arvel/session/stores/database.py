"""Database-backed session store (SQLAlchemy async)."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any, cast

import sqlalchemy as sa
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

if TYPE_CHECKING:
    from arvel.session.cipher import SessionCipher

_sessions_table = sa.Table(
    "sessions",
    sa.MetaData(),
    sa.Column("id", sa.String(128), primary_key=True),
    sa.Column("payload", sa.Text, nullable=False),
    sa.Column("last_activity", sa.Integer, nullable=False),
)


class DatabaseSessionStore:
    """Session store backed by an SQL ``sessions`` table."""

    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        lifetime: int = 7200,
        *,
        cipher: SessionCipher | None = None,
    ) -> None:
        self.session_maker = session_maker
        self.lifetime = lifetime
        self._cipher = cipher

    async def create_table(self, engine: AsyncEngine) -> None:
        """Create the sessions table if it doesn't exist."""
        async with engine.begin() as conn:
            await conn.run_sync(_sessions_table.metadata.create_all)

    async def read(self, session_id: str) -> dict[str, Any]:
        async with self.session_maker() as session:
            row = await session.execute(
                sa.select(_sessions_table).where(_sessions_table.c.id == session_id)
            )
            record = row.first()
        if record is None:
            return {}
        # Expire on read so a stale row is treated as empty before GC sweeps it.
        if self.lifetime > 0 and record.last_activity < int(time.time()) - self.lifetime:
            return {}
        try:
            if self._cipher is not None:
                return self._cipher.decrypt(record.payload)
            raw: Any = json.loads(record.payload)
            return cast("dict[str, Any]", raw) if isinstance(raw, dict) else {}
        except json.JSONDecodeError, ValueError, TypeError:
            return {}

    async def write(self, session_id: str, data: dict[str, Any]) -> None:
        now = int(time.time())
        payload = self._cipher.encrypt(data) if self._cipher is not None else json.dumps(data)
        async with self.session_maker() as session, session.begin():
            existing = await session.execute(
                sa.select(_sessions_table).where(_sessions_table.c.id == session_id)
            )
            if existing.first():
                await session.execute(
                    sa.update(_sessions_table)
                    .where(_sessions_table.c.id == session_id)
                    .values(payload=payload, last_activity=now)
                )
            else:
                await session.execute(
                    sa.insert(_sessions_table).values(
                        id=session_id, payload=payload, last_activity=now
                    )
                )

    async def destroy(self, session_id: str) -> None:
        async with self.session_maker() as session, session.begin():
            await session.execute(
                sa.delete(_sessions_table).where(_sessions_table.c.id == session_id)
            )

    async def gc(self, max_lifetime: int) -> int:
        cutoff = int(time.time()) - max_lifetime
        async with self.session_maker() as session, session.begin():
            result = cast(
                "CursorResult[Any]",
                await session.execute(
                    sa.delete(_sessions_table).where(_sessions_table.c.last_activity < cutoff)
                ),
            )
        return int(result.rowcount)


__all__ = ["DatabaseSessionStore"]
