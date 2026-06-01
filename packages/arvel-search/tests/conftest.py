"""Fixtures for arvel-search tests — table setup, facade reset, engine binding."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from arvel.database import Model
from arvel_search import Search, SearchManager
from search_support import make_config
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.fixture(autouse=True)
def reset_search() -> Iterator[None]:
    """Unbind any engine/fake between tests. Observer hooks stay wired."""
    yield
    Search.restore()
    Search.manager = None


@pytest_asyncio.fixture
async def tables(engine: AsyncEngine) -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    yield


@pytest.fixture
def collection_engine() -> SearchManager:
    manager = SearchManager(make_config(driver="collection"))
    Search.bind(manager)
    return manager
