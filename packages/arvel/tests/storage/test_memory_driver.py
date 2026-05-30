"""Tests for MemoryDriver — FR-006-028."""

from __future__ import annotations

import pytest
from arvel.storage.drivers.memory import MemoryDriver


@pytest.fixture
def driver() -> MemoryDriver:
    return MemoryDriver()


class TestMemoryDriverBasicOps:
    @pytest.mark.asyncio
    async def test_put_and_get_bytes(self, driver: MemoryDriver) -> None:
        await driver.put("file.txt", b"hello")
        assert await driver.get("file.txt") == b"hello"

    @pytest.mark.asyncio
    async def test_put_string_content(self, driver: MemoryDriver) -> None:
        await driver.put("file.txt", "hello")
        assert await driver.get("file.txt") == b"hello"

    @pytest.mark.asyncio
    async def test_exists_true(self, driver: MemoryDriver) -> None:
        await driver.put("f.txt", b"x")
        assert await driver.exists("f.txt") is True

    @pytest.mark.asyncio
    async def test_exists_false(self, driver: MemoryDriver) -> None:
        assert await driver.exists("nonexistent.txt") is False

    @pytest.mark.asyncio
    async def test_delete(self, driver: MemoryDriver) -> None:
        await driver.put("del.txt", b"bye")
        await driver.delete("del.txt")
        assert await driver.exists("del.txt") is False

    @pytest.mark.asyncio
    async def test_copy(self, driver: MemoryDriver) -> None:
        await driver.put("src.txt", b"source")
        await driver.copy("src.txt", "dst.txt")
        assert await driver.get("dst.txt") == b"source"
        assert await driver.exists("src.txt") is True

    @pytest.mark.asyncio
    async def test_move(self, driver: MemoryDriver) -> None:
        await driver.put("mv_src.txt", b"data")
        await driver.move("mv_src.txt", "mv_dst.txt")
        assert await driver.get("mv_dst.txt") == b"data"
        assert await driver.exists("mv_src.txt") is False

    @pytest.mark.asyncio
    async def test_files(self, driver: MemoryDriver) -> None:
        await driver.put("dir/a.txt", b"a")
        await driver.put("dir/b.txt", b"b")
        await driver.put("other/c.txt", b"c")
        files = await driver.files("dir/")
        assert set(files) == {"dir/a.txt", "dir/b.txt"}

    @pytest.mark.asyncio
    async def test_size(self, driver: MemoryDriver) -> None:
        await driver.put("sized.txt", b"12345")
        assert await driver.size("sized.txt") == 5

    @pytest.mark.asyncio
    async def test_get_missing_raises(self, driver: MemoryDriver) -> None:
        from arvel.storage.exceptions import FileNotFoundError as StorageFileNotFoundError

        with pytest.raises(StorageFileNotFoundError):
            await driver.get("missing.txt")
