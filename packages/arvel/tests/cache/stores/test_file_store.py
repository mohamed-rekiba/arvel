"""Tests for FileStore — FR-006-003."""

from __future__ import annotations

from pathlib import Path

import pytest
from arvel.cache.stores.file import FileStore


@pytest.fixture
def store(tmp_path: Path) -> FileStore:
    return FileStore(path=tmp_path, prefix="test")


class TestFileStoreBasicOps:
    @pytest.mark.asyncio
    async def test_put_get_roundtrip(self, store: FileStore) -> None:
        await store.put("k", "v")
        assert await store.get("k") == "v"

    @pytest.mark.asyncio
    async def test_missing_returns_none(self, store: FileStore) -> None:
        assert await store.get("missing") is None

    @pytest.mark.asyncio
    async def test_has_present(self, store: FileStore) -> None:
        await store.put("x", 1)
        assert await store.has("x") is True

    @pytest.mark.asyncio
    async def test_forget(self, store: FileStore, tmp_path: Path) -> None:
        await store.put("del", "v")
        await store.forget("del")
        assert await store.has("del") is False

    @pytest.mark.asyncio
    async def test_flush(self, store: FileStore) -> None:
        await store.put("a", 1)
        await store.put("b", 2)
        await store.flush()
        assert await store.has("a") is False

    @pytest.mark.asyncio
    async def test_forever_no_expiry(self, store: FileStore) -> None:
        await store.forever("eternal", "v")
        assert await store.get("eternal") == "v"

    @pytest.mark.asyncio
    async def test_file_created_on_disk(self, store: FileStore, tmp_path: Path) -> None:
        await store.put("persisted", "yes")
        cache_files = list(tmp_path.glob("*.json"))
        assert len(cache_files) >= 1

    @pytest.mark.asyncio
    async def test_tags_not_supported(self, store: FileStore) -> None:
        from arvel.cache.exceptions import TagsNotSupported

        with pytest.raises(TagsNotSupported):
            store.tags(["posts"])
