"""Materialized view framework with pg_ivm auto-refresh support.

Provides a MaterializedView abstract base, a ViewRegistry for
self-registration, and pg_ivm detection with graceful fallback.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar


class MaterializedView(ABC):
    """Abstract base for materialized views.

    Subclass, set ``__viewname__``, and implement ``query_definition()``::

        class ActiveUserStats(MaterializedView):
            __viewname__ = "active_user_stats"

            @classmethod
            def query_definition(cls) -> Select:
                return select(User.id, func.count(Post.id)).join(...).group_by(User.id)
    """

    __viewname__: ClassVar[str]
    readonly: ClassVar[bool] = True

    @classmethod
    @abstractmethod
    def query_definition(cls) -> Any:
        """Return a SQLAlchemy select() defining the view."""
        ...


class ViewRegistry:
    """Registry for materialized view classes."""

    def __init__(self) -> None:
        self._views: dict[str, type[MaterializedView]] = {}

    def register(self, view_cls: type[MaterializedView]) -> None:
        name = view_cls.__viewname__
        if not name.replace("_", "").isalnum():
            msg = f"Invalid view name: {name!r} (must be alphanumeric + underscores)"
            raise ValueError(msg)
        self._views[name] = view_cls

    def all(self) -> list[type[MaterializedView]]:
        return list(self._views.values())

    def get(self, name: str) -> type[MaterializedView] | None:
        return self._views.get(name)

    async def refresh(self, name: str, *, db_url: str) -> dict[str, Any]:
        """Refresh a single materialized view by name.

        On SQLite this is a no-op that returns a status dict.
        On PostgreSQL this executes REFRESH MATERIALIZED VIEW.
        """
        view_cls = self.get(name)
        if view_cls is None:
            msg = f"View '{name}' not found in registry"
            raise KeyError(msg)

        is_pg = "postgresql" in db_url or "asyncpg" in db_url

        if is_pg:
            from sqlalchemy import text
            from sqlalchemy.ext.asyncio import create_async_engine

            engine = create_async_engine(db_url, echo=False)
            try:
                async with engine.connect() as conn:
                    await conn.execute(text(f"REFRESH MATERIALIZED VIEW {view_cls.__viewname__}"))
                    await conn.commit()
            finally:
                await engine.dispose()

        return {"view": name, "refreshed": is_pg, "status": "ok"}

    async def refresh_all(self, *, db_url: str) -> list[dict[str, Any]]:
        """Refresh all registered views."""
        results = []
        for name in self._views:
            result = await self.refresh(name, db_url=db_url)
            results.append(result)
        return results


async def detect_pg_ivm(db_url: str) -> bool:
    """Check if the pg_ivm extension is available.

    Returns False for non-PostgreSQL databases.
    """
    if "postgresql" not in db_url and "asyncpg" not in db_url:
        return False

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(db_url, echo=False)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'pg_ivm'"))
            row = result.fetchone()
            return row is not None
    except Exception:
        return False
    finally:
        await engine.dispose()
