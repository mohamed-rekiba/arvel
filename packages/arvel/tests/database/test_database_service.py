"""``DatabaseService`` — adapter that exposes the engine to ``/_health``."""

from __future__ import annotations

import pytest
from arvel.container.container import Container
from arvel.database.service import DatabaseService
from arvel.services import HealthStatus
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


@pytest.fixture
def container() -> Container:
    return Container()


async def test_health_check_returns_healthy_when_engine_reachable(
    container: Container,
) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    container.instance(AsyncEngine, engine)
    try:
        result = await DatabaseService(container).health_check()
    finally:
        await engine.dispose()

    assert result.status is HealthStatus.healthy
    assert result.detail is None


async def test_health_check_returns_unhealthy_on_sqlalchemy_error(
    container: Container,
) -> None:
    # Path the SQLite driver can't open — connect() raises SQLAlchemyError.
    engine = create_async_engine("sqlite+aiosqlite:////nonexistent-arvel-dir/x.db")
    container.instance(AsyncEngine, engine)
    try:
        result = await DatabaseService(container).health_check()
    finally:
        await engine.dispose()

    assert result.status is HealthStatus.unhealthy
    # Detail stays generic — raw errors can leak host/URL (A10).
    assert result.detail == "database unreachable"


def test_service_has_stable_name() -> None:
    # Health endpoint aggregates by this name; keep it pinned.
    assert DatabaseService.name == "database"
