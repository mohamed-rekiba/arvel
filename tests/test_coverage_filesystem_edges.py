"""Coverage-closing behavioral tests for `arvel.filesystem`: the disk-relative-path fallback
for an unrelated path, root-level writes/copies/moves (no parent directory to create),
`last_modified`'s datetime/string `mtime` shapes, an idempotent `delete_directory` on a path
that never existed, the non-s3/non-local `get_visibility` default fallback, and
`temporary_url` raising on a driver that doesn't support presigned URLs. All on
memory/local fsspec backends — no cloud driver is faked."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import fsspec
import pytest

from arvel.filesystem import Filesystem, UnsupportedDriverOperation, Visibility


def test_relative_path_unrelated_to_root_passes_through_unchanged() -> None:
    disk = Filesystem(fsspec.filesystem("memory"), root="myroot")
    # a full path that shares no prefix with the root and isn't the root itself
    assert disk._relative("elsewhere/file.txt") == "elsewhere/file.txt"


async def test_put_copy_move_write_stream_at_root_level_skip_makedirs() -> None:
    disk = Filesystem(fsspec.filesystem("memory"), root="")
    try:
        await disk.put("root-file.txt", "hi")  # no "/" in the full path: parent == ""
        assert await disk.get("root-file.txt") == b"hi"

        await disk.copy("root-file.txt", "root-copy.txt")
        assert await disk.get("root-copy.txt") == b"hi"

        await disk.move("root-copy.txt", "root-moved.txt")
        assert await disk.get("root-moved.txt") == b"hi"
        assert not await disk.exists("root-copy.txt")

        async def _one_chunk() -> Any:
            yield b"streamed"

        await disk.write_stream("root-stream.txt", _one_chunk())
        assert await disk.get("root-stream.txt") == b"streamed"
    finally:
        for name in ("root-file.txt", "root-moved.txt", "root-stream.txt"):
            await disk.delete(name)


class _InfoStubFS:
    """A minimal fsspec-shaped stub exposing only what `last_modified` touches."""

    protocol = "stub"

    def __init__(self, info: dict[str, Any]) -> None:
        self._info = info

    def info(self, _path: str) -> dict[str, Any]:
        return self._info


async def test_last_modified_accepts_a_native_datetime_mtime() -> None:
    stamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    disk = Filesystem(_InfoStubFS({"mtime": stamp}), root="")
    result = await disk.last_modified("x")
    assert result.to_py() == stamp


async def test_last_modified_accepts_an_iso_string_last_modified() -> None:
    disk = Filesystem(_InfoStubFS({"LastModified": "2026-01-02T03:04:05+00:00"}), root="")
    result = await disk.last_modified("x")
    assert result.to_py() == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


async def test_delete_directory_on_a_path_that_never_existed_is_idempotent() -> None:
    disk = Filesystem(fsspec.filesystem("memory"), root="")
    assert await disk.delete_directory("never/existed") is True


async def test_get_visibility_falls_back_to_the_disk_default_for_other_drivers() -> None:
    disk = Filesystem(fsspec.filesystem("memory"), root="", default_visibility=Visibility.PRIVATE)
    # memory's protocol is neither file/local nor s3/s3a: no per-object ACL, so this
    # reports the disk's configured default without touching the filesystem at all
    assert await disk.get_visibility("whatever.txt") == Visibility.PRIVATE


async def test_temporary_url_raises_on_a_driver_without_presigned_urls(tmp_path: Path) -> None:
    disk = Filesystem(fsspec.filesystem("file"), root=str(tmp_path))
    with pytest.raises(UnsupportedDriverOperation):
        await disk.temporary_url("a.txt", timedelta(minutes=5))
