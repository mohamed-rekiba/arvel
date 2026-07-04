"""FS-RICH (doc 04) — the full Storage disk surface, exercised on the local fsspec driver."""

from __future__ import annotations

import os
import stat
from datetime import timedelta
from pathlib import Path

import fsspec
import pytest

from arvel.dates import Date
from arvel.filesystem import Filesystem, UnsupportedDriverOperation, Visibility


def _disk(tmp_path: Path, **kwargs: object) -> Filesystem:
    return Filesystem(fsspec.filesystem("file"), root=str(tmp_path), **kwargs)  # type: ignore[arg-type]


# -- content --------------------------------------------------------------------------------


async def test_append_creates_then_appends(tmp_path: Path) -> None:
    disk = _disk(tmp_path)
    await disk.append("log.txt", "first")
    assert await disk.get("log.txt") == b"first"
    await disk.append("log.txt", "-second")
    assert await disk.get("log.txt") == b"first-second"


async def test_prepend_creates_then_prepends(tmp_path: Path) -> None:
    disk = _disk(tmp_path)
    await disk.prepend("log.txt", "b")
    assert await disk.get("log.txt") == b"b"
    await disk.prepend("log.txt", "a")
    assert await disk.get("log.txt") == b"ab"


async def test_put_file_bytes_generates_random_name(tmp_path: Path) -> None:
    disk = _disk(tmp_path)
    path = await disk.put_file("avatars", b"\x00\x01")
    assert path.startswith(f"{tmp_path}/avatars/")
    assert await disk.get(path.removeprefix(f"{tmp_path}/")) == b"\x00\x01"


class _FakeUpload:
    """Duck-types the bits of ``UploadedFile`` that ``put_file`` needs."""

    def __init__(self, data: bytes, extension: str) -> None:
        self._data = data
        self.extension = extension

    async def read(self) -> bytes:
        return self._data


async def test_put_file_uploadedfile_like_keeps_extension(tmp_path: Path) -> None:
    disk = _disk(tmp_path)
    upload = _FakeUpload(b"png-bytes", "png")
    path = await disk.put_file("avatars", upload)
    assert path.endswith(".png")
    assert await disk.exists(path.removeprefix(f"{tmp_path}/"))


async def test_put_file_explicit_name(tmp_path: Path) -> None:
    disk = _disk(tmp_path)
    path = await disk.put_file("avatars", b"data", name="ada.png")
    assert path == f"{tmp_path}/avatars/ada.png"


# -- metadata ---------------------------------------------------------------------------------


async def test_size_and_missing(tmp_path: Path) -> None:
    disk = _disk(tmp_path)
    await disk.put("a.txt", b"12345")
    assert await disk.size("a.txt") == 5
    assert await disk.missing("a.txt") is False
    assert await disk.missing("nope.txt") is True


async def test_size_raises_file_not_found(tmp_path: Path) -> None:
    disk = _disk(tmp_path)
    with pytest.raises(FileNotFoundError):
        await disk.size("nope.txt")


async def test_last_modified_returns_arvel_date(tmp_path: Path) -> None:
    disk = _disk(tmp_path)
    await disk.put("a.txt", b"x")
    modified = await disk.last_modified("a.txt")
    assert isinstance(modified, Date)
    now_epoch = Date.now().to_py().timestamp()
    assert abs(modified.to_py().timestamp() - now_epoch) < 60


@pytest.mark.parametrize(
    ("name", "expected"),
    [("a.txt", "text/plain"), ("a.png", "image/png"), ("a.unknownext", "application/octet-stream")],
)
async def test_mime_type(tmp_path: Path, name: str, expected: str) -> None:
    disk = _disk(tmp_path)
    assert await disk.mime_type(name) == expected


# -- copy / move ------------------------------------------------------------------------------


async def test_copy_leaves_source_in_place(tmp_path: Path) -> None:
    disk = _disk(tmp_path)
    await disk.put("src.txt", b"data")
    await disk.copy("src.txt", "nested/dst.txt")
    assert await disk.get("nested/dst.txt") == b"data"
    assert await disk.exists("src.txt") is True


async def test_move_removes_source(tmp_path: Path) -> None:
    disk = _disk(tmp_path)
    await disk.put("src.txt", b"data")
    await disk.move("src.txt", "nested/dst.txt")
    assert await disk.get("nested/dst.txt") == b"data"
    assert await disk.exists("src.txt") is False


# -- listing (relative to disk root, nested tree) ----------------------------------------------


async def test_listing_nested_tree_is_relative_to_root(tmp_path: Path) -> None:
    disk = _disk(tmp_path)
    await disk.put("a.txt", b"1")
    await disk.put("docs/b.txt", b"2")
    await disk.put("docs/sub/c.txt", b"3")

    assert await disk.files("") == ["a.txt"]
    assert await disk.directories("") == ["docs"]
    assert sorted(await disk.all_files("")) == ["a.txt", "docs/b.txt", "docs/sub/c.txt"]
    assert sorted(await disk.all_directories("")) == ["docs", "docs/sub"]
    assert await disk.files("docs") == ["docs/b.txt"]


async def test_files_on_missing_directory_returns_empty(tmp_path: Path) -> None:
    disk = _disk(tmp_path)
    assert await disk.files("nope") == []
    assert await disk.all_files("nope") == []
    assert await disk.directories("nope") == []
    assert await disk.all_directories("nope") == []


async def test_make_directory_and_delete_directory(tmp_path: Path) -> None:
    disk = _disk(tmp_path)
    await disk.make_directory("empty")
    assert await disk.directories("") == ["empty"]

    await disk.put("todelete/a.txt", b"1")
    await disk.put("todelete/sub/b.txt", b"2")
    await disk.delete_directory("todelete")
    assert await disk.exists("todelete/a.txt") is False
    assert await disk.exists("todelete/sub/b.txt") is False


# -- streaming ---------------------------------------------------------------------------------


async def test_read_stream_yields_multiple_chunks(tmp_path: Path) -> None:
    disk = _disk(tmp_path)
    payload = b"x" * 250
    await disk.put("big.bin", payload)

    chunks = [chunk async for chunk in disk.read_stream("big.bin", chunk_size=100)]
    assert len(chunks) == 3
    assert chunks[0] == b"x" * 100
    assert chunks[-1] == b"x" * 50
    assert b"".join(chunks) == payload


async def test_write_stream_from_async_iterable(tmp_path: Path) -> None:
    disk = _disk(tmp_path)

    async def _source() -> object:
        for chunk in (b"one-", b"two-", b"three"):
            yield chunk

    path = await disk.write_stream("streamed.bin", _source())
    assert await disk.get(path.removeprefix(f"{tmp_path}/")) == b"one-two-three"


# -- visibility ---------------------------------------------------------------------------------


async def test_set_and_get_visibility_local(tmp_path: Path) -> None:
    disk = _disk(tmp_path)
    await disk.put("a.txt", b"x")

    await disk.set_visibility("a.txt", Visibility.PRIVATE)
    assert await disk.get_visibility("a.txt") is Visibility.PRIVATE
    mode = stat.S_IMODE(os.stat(tmp_path / "a.txt").st_mode)
    assert mode == 0o600

    await disk.set_visibility("a.txt", Visibility.PUBLIC)
    assert await disk.get_visibility("a.txt") is Visibility.PUBLIC
    mode = stat.S_IMODE(os.stat(tmp_path / "a.txt").st_mode)
    assert mode == 0o644


# -- URLs -----------------------------------------------------------------------------------


async def test_url_uses_config_override(tmp_path: Path) -> None:
    disk = _disk(tmp_path, url="https://cdn.example.com")
    assert disk.url("a/b.png") == "https://cdn.example.com/a/b.png"


async def test_url_local_without_override_returns_full_path(tmp_path: Path) -> None:
    disk = _disk(tmp_path)
    assert disk.url("a.png") == f"{tmp_path}/a.png"


async def test_temporary_url_unsupported_on_local(tmp_path: Path) -> None:
    disk = _disk(tmp_path)
    with pytest.raises(UnsupportedDriverOperation):
        await disk.temporary_url("a.png", timedelta(minutes=5))
