"""Phase 6 — Storage manager (fsspec-backed) behaviour."""

from __future__ import annotations

from pathlib import Path

import fsspec
import pytest

from arvel.filesystem import Filesystem, FilesystemManager
from arvel.support.manager import MissingExtraError


async def test_local_disk_roundtrip(tmp_path: Path) -> None:
    disk = Filesystem(fsspec.filesystem("file"), root=str(tmp_path))
    path = await disk.put("uploads/a.txt", "hello")
    assert path.endswith("uploads/a.txt")
    assert await disk.exists("uploads/a.txt")
    assert await disk.get("uploads/a.txt") == b"hello"
    await disk.delete("uploads/a.txt")
    assert not await disk.exists("uploads/a.txt")


async def test_delete_missing_path_is_idempotent(tmp_path: Path) -> None:
    disk = Filesystem(fsspec.filesystem("file"), root=str(tmp_path))
    # deleting something that isn't there is a no-op success, not a FileNotFoundError
    assert await disk.delete("nope.txt") is True


async def test_put_bytes(tmp_path: Path) -> None:
    disk = Filesystem(fsspec.filesystem("file"), root=str(tmp_path))
    await disk.put("b.bin", b"\x00\x01\x02")
    assert await disk.get("b.bin") == b"\x00\x01\x02"


def test_manager_defaults_to_local_disk() -> None:
    manager = FilesystemManager()
    assert manager.default_driver() == "local"
    assert isinstance(manager.disk(), Filesystem)


def test_missing_disk_driver_raises() -> None:
    with pytest.raises(MissingExtraError):
        FilesystemManager().disk("dropbox")
