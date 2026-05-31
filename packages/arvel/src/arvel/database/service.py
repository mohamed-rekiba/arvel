"""DatabaseService — exposes the SQLAlchemy engine's health to ``/_health``.

The engine's lifecycle stays with ``DatabaseServiceProvider`` (it builds the
engine lazily and disposes it on shutdown). This adapter only adds a health
probe so the database shows up in the aggregated health report.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.services import BaseService, HealthResult, HealthStatus

if TYPE_CHECKING:
    from arvel.container import Container


class DatabaseService(BaseService):
    name = "database"

    def __init__(self, container: Container) -> None:
        self._container = container

    async def health_check(self) -> HealthResult:
        from sqlalchemy import text
        from sqlalchemy.exc import SQLAlchemyError
        from sqlalchemy.ext.asyncio import AsyncEngine

        engine = self._container.make(AsyncEngine)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except SQLAlchemyError:
            # Clean detail only — raw errors can leak the host/URL (A10).
            return HealthResult(HealthStatus.unhealthy, "database unreachable")
        return HealthResult(HealthStatus.healthy)


__all__ = ["DatabaseService"]
