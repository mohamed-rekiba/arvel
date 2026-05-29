"""Cache conftest — shared fixtures."""

from __future__ import annotations

import pytest
import pytest_asyncio
from arvel.cache import CacheManager
from arvel.cache.stores.array import ArrayStore
from arvel.cache.stores.null import NullStore
from arvel.config.cache_config import CacheConfig, CacheDriver


@pytest.fixture
def array_store() -> ArrayStore:
    return ArrayStore(prefix="test")


@pytest.fixture
def null_store() -> NullStore:
    return NullStore()


@pytest_asyncio.fixture
async def cache_manager() -> CacheManager:
    config = CacheConfig(connection=CacheDriver.ARRAY)
    return CacheManager(config)
