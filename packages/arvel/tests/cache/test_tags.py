"""Tests for TaggedCache — FR-006-008."""

from __future__ import annotations

import pytest
from arvel.cache import CacheManager
from arvel.cache.exceptions import TagsNotSupported
from arvel.config.cache_config import CacheConfig, CacheDriver


@pytest.fixture
def manager() -> CacheManager:
    return CacheManager(CacheConfig(connection=CacheDriver.ARRAY))


class TestTaggedCacheBasicOps:
    @pytest.mark.asyncio
    async def test_tagged_put_and_get(self, manager: CacheManager) -> None:
        await manager.tags(["posts"]).put("post:1", {"title": "Hello"}, ttl=60)
        result = await manager.tags(["posts"]).get("post:1")
        assert result == {"title": "Hello"}

    @pytest.mark.asyncio
    async def test_tagged_forget(self, manager: CacheManager) -> None:
        await manager.tags(["posts"]).put("post:2", "data")
        await manager.tags(["posts"]).forget("post:2")
        assert await manager.tags(["posts"]).get("post:2") is None

    @pytest.mark.asyncio
    async def test_tag_flush_invalidates_tagged_keys(self, manager: CacheManager) -> None:
        await manager.tags(["posts"]).put("post:3", "data")
        await manager.tags(["users"]).put("user:1", "data")
        await manager.tags(["posts"]).flush()

        # Post key unreachable after tag flush
        assert await manager.tags(["posts"]).get("post:3") is None
        # User key unaffected
        assert await manager.tags(["users"]).get("user:1") == "data"

    @pytest.mark.asyncio
    async def test_multiple_tags(self, manager: CacheManager) -> None:
        await manager.tags(["posts", "user:1"]).put("feed", [1, 2, 3], ttl=60)
        result = await manager.tags(["posts", "user:1"]).get("feed")
        assert result == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_flush_one_tag_keeps_other(self, manager: CacheManager) -> None:
        await manager.tags(["posts", "user:1"]).put("shared", "data")
        await manager.tags(["posts"]).flush()
        # Key under ["posts", "user:1"] is now stale (posts tag rotated)
        assert await manager.tags(["posts", "user:1"]).get("shared") is None


class TestTaggedCacheUnsupportedStores:
    @pytest.mark.asyncio
    async def test_file_store_raises_tags_not_supported(self, tmp_path: object) -> None:
        from pathlib import Path

        from arvel.cache.stores.file import FileStore

        store = FileStore(path=Path(str(tmp_path)), prefix="t")
        with pytest.raises(TagsNotSupported):
            store.tags(["posts"])

    @pytest.mark.asyncio
    async def test_null_store_raises_tags_not_supported(self) -> None:
        from arvel.cache.stores.null import NullStore

        with pytest.raises(TagsNotSupported):
            NullStore().tags(["posts"])
