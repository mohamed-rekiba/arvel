"""Tests for LocalDriver."""

from __future__ import annotations

from pathlib import Path

import pytest
from arvel.storage.drivers.local import LocalDriver
from arvel.storage.exceptions import StoragePathError


@pytest.fixture
def driver(tmp_path: Path) -> LocalDriver:
    return LocalDriver(root=tmp_path, base_url="http://localhost:8000")


class TestLocalDriverBasicOps:
    @pytest.mark.asyncio
    async def test_put_and_get(self, driver: LocalDriver) -> None:
        await driver.put("file.txt", b"hello")
        assert await driver.get("file.txt") == b"hello"

    @pytest.mark.asyncio
    async def test_put_string_content(self, driver: LocalDriver) -> None:
        await driver.put("file.txt", "hello string")
        result = await driver.get("file.txt")
        assert result == b"hello string"

    @pytest.mark.asyncio
    async def test_exists_true(self, driver: LocalDriver) -> None:
        await driver.put("f.txt", b"x")
        assert await driver.exists("f.txt") is True

    @pytest.mark.asyncio
    async def test_exists_false(self, driver: LocalDriver) -> None:
        assert await driver.exists("nonexistent.txt") is False

    @pytest.mark.asyncio
    async def test_delete(self, driver: LocalDriver) -> None:
        await driver.put("del.txt", b"bye")
        await driver.delete("del.txt")
        assert await driver.exists("del.txt") is False

    @pytest.mark.asyncio
    async def test_copy(self, driver: LocalDriver) -> None:
        await driver.put("src.txt", b"source")
        await driver.copy("src.txt", "dst.txt")
        assert await driver.get("dst.txt") == b"source"

    @pytest.mark.asyncio
    async def test_move(self, driver: LocalDriver) -> None:
        await driver.put("mv_src.txt", b"data")
        await driver.move("mv_src.txt", "mv_dst.txt")
        assert await driver.get("mv_dst.txt") == b"data"
        assert await driver.exists("mv_src.txt") is False

    @pytest.mark.asyncio
    async def test_files_lists_prefix(self, driver: LocalDriver) -> None:
        await driver.put("invoices/001.pdf", b"pdf1")
        await driver.put("invoices/002.pdf", b"pdf2")
        await driver.put("images/logo.png", b"png")
        files = await driver.files("invoices/")
        assert set(files) == {"invoices/001.pdf", "invoices/002.pdf"}

    @pytest.mark.asyncio
    async def test_size(self, driver: LocalDriver) -> None:
        await driver.put("sized.txt", b"12345")
        assert await driver.size("sized.txt") == 5

    @pytest.mark.asyncio
    async def test_nested_directory_created(self, driver: LocalDriver, tmp_path: Path) -> None:
        await driver.put("deep/nested/file.txt", b"deep")
        assert (tmp_path / "deep" / "nested" / "file.txt").exists()


class TestLocalDriverPathTraversal:
    """Path traversal prevention ()."""

    @pytest.mark.asyncio
    async def test_traversal_above_root_raises(self, driver: LocalDriver) -> None:
        with pytest.raises(StoragePathError):
            await driver.get("../../etc/passwd")

    @pytest.mark.asyncio
    async def test_absolute_path_raises(self, driver: LocalDriver) -> None:
        with pytest.raises(StoragePathError):
            await driver.get("/etc/passwd")

    @pytest.mark.asyncio
    async def test_null_byte_raises(self, driver: LocalDriver) -> None:
        with pytest.raises((StoragePathError, ValueError)):
            await driver.get("file\x00.txt")

    @pytest.mark.asyncio
    async def test_encoded_traversal_raises(self, driver: LocalDriver) -> None:
        with pytest.raises(StoragePathError):
            await driver.get("..%2F..%2Fetc%2Fpasswd")


class TestLocalDriverURL:
    def test_url_returns_public_url(self, driver: LocalDriver) -> None:
        url = driver.url("invoices/001.pdf")
        assert url.startswith("http://localhost:8000")
        assert "invoices/001.pdf" in url
