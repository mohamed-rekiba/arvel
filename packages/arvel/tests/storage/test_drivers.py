"""Storage driver behavior."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from arvel.storage.drivers.local import LocalDriver
from arvel.storage.drivers.memory import MemoryDriver
from arvel.storage.exceptions import FileNotFoundError as StorageFileNotFoundError
from arvel.storage.exceptions import StoragePathError


async def test_memory_driver_full_file_lifecycle() -> None:
    driver = MemoryDriver()

    assert await driver.exists("docs/a.txt") is False
    with pytest.raises(StorageFileNotFoundError):
        await driver.get("docs/a.txt")

    assert await driver.put("docs/a.txt", "hello") is True
    assert await driver.put("docs/b.txt", b"bytes") is True
    assert await driver.put("images/c.bin", BytesIO(b"stream")) is True
    assert await driver.exists("docs/a.txt") is True
    assert await driver.get("docs/a.txt") == b"hello"
    assert await driver.size("images/c.bin") == 6
    assert sorted(await driver.files("docs")) == ["docs/a.txt", "docs/b.txt"]
    assert sorted(await driver.list()) == ["docs/a.txt", "docs/b.txt", "images/c.bin"]
    assert await driver.copy("missing", "copy") is False
    assert await driver.copy("docs/a.txt", "docs/c.txt") is True
    assert await driver.move("missing", "moved") is False
    assert await driver.move("docs/c.txt", "docs/d.txt") is True
    assert await driver.delete("missing") is False
    assert await driver.delete("docs/d.txt") is True
    assert driver.url("docs/a.txt") == "memory://docs/a.txt"
    assert driver.temporary_url("docs/a.txt", 60) == "memory://docs/a.txt?tmp=1"


async def test_memory_driver_size_missing_raises() -> None:
    with pytest.raises(StorageFileNotFoundError):
        await MemoryDriver().size("missing.txt")


async def test_local_driver_full_file_lifecycle(tmp_path: Path) -> None:
    driver = LocalDriver(tmp_path, base_url="https://cdn.test/storage", app_key=b"k" * 32)

    assert await driver.exists("docs/a.txt") is False
    with pytest.raises(StorageFileNotFoundError):
        await driver.get("docs/a.txt")

    assert await driver.put("docs/a.txt", "hello") is True
    assert await driver.put("docs/b.txt", b"bytes") is True
    assert await driver.put("images/c.bin", BytesIO(b"stream")) is True
    assert await driver.exists("docs/a.txt") is True
    assert await driver.get("docs/a.txt") == b"hello"
    assert await driver.size("images/c.bin") == 6
    assert sorted(await driver.files("docs")) == ["docs/a.txt", "docs/b.txt"]
    assert sorted(await driver.list()) == ["docs/a.txt", "docs/b.txt", "images/c.bin"]
    assert await driver.copy("missing", "copy") is False
    assert await driver.copy("docs/a.txt", "docs/c.txt") is True
    assert await driver.move("missing", "moved") is False
    assert await driver.move("docs/c.txt", "docs/d.txt") is True
    assert await driver.delete("missing") is False
    assert await driver.delete("docs/d.txt") is True
    assert driver.url("/docs/a.txt") == "https://cdn.test/storage/docs/a.txt"
    signed = driver.temporary_url("docs/a.txt", 60)
    assert "token=" in signed
    assert "expires=" in signed


async def test_local_driver_size_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(StorageFileNotFoundError):
        await LocalDriver(tmp_path).size("missing.txt")


async def test_local_missing_is_catchable_as_builtin(tmp_path: Path) -> None:
    # StorageFileNotFoundError subclasses the builtin, so disk-agnostic
    # callers can catch either type across every driver.
    driver = LocalDriver(tmp_path)
    with pytest.raises(FileNotFoundError):
        await driver.get("missing.txt")


async def test_local_driver_blocks_path_traversal(tmp_path: Path) -> None:
    driver = LocalDriver(tmp_path)

    for path in ("../secret.txt", "%2e%2e/secret.txt", "/absolute.txt", "bad\x00name"):
        with pytest.raises(StoragePathError):
            await driver.exists(path)


def test_local_driver_requires_key_for_temporary_urls(tmp_path: Path) -> None:
    driver = LocalDriver(tmp_path)

    with pytest.raises(RuntimeError, match="requires app_key"):
        driver.temporary_url("docs/a.txt", 60)
