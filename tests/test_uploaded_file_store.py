"""C4 — UploadedFile.store()/store_as() persist an upload to a disk via the filesystem
manager and return the stored path. Test-first."""

from __future__ import annotations

from typing import Any

import fsspec
import pytest

from arvel.filesystem import Filesystem
from arvel.http import UploadedFile
from arvel.kernel import Application, set_application


class _FakeUpload:
    """Stands in for a Litestar UploadFile."""

    def __init__(self, filename: str, data: bytes) -> None:
        self.filename = filename
        self.content_type = "text/plain"
        self._data = data

    async def read(self) -> bytes:
        return self._data


class _FixedDiskManager:
    """A filesystem manager whose ``disk()`` always returns the same local disk."""

    def __init__(self, disk: Filesystem) -> None:
        self._disk = disk

    def disk(self, name: str | None = None) -> Filesystem:
        return self._disk


@pytest.fixture
def app_with_disk(tmp_path: Any) -> Any:
    disk = Filesystem(fsspec.filesystem("file"), root=str(tmp_path))
    app = Application()
    app.instance("filesystem", _FixedDiskManager(disk))
    set_application(app)
    try:
        yield disk
    finally:
        set_application(None)


async def test_store_writes_to_disk_and_returns_path(app_with_disk: Filesystem) -> None:
    upload = UploadedFile(_FakeUpload("avatar.png", b"PNG-BYTES"))
    path = await upload.store("avatars")
    assert path.startswith("avatars/")
    assert path.endswith(".png")  # original extension preserved
    assert await app_with_disk.get(path) == b"PNG-BYTES"


async def test_store_as_uses_explicit_name(app_with_disk: Filesystem) -> None:
    upload = UploadedFile(_FakeUpload("report.pdf", b"%PDF"))
    path = await upload.store_as("docs", "q3.pdf")
    assert path == "docs/q3.pdf"
    assert await app_with_disk.get("docs/q3.pdf") == b"%PDF"


def test_metadata_accessors() -> None:
    upload = UploadedFile(_FakeUpload("photo.JPG", b""))
    assert upload.client_name == "photo.JPG"
    assert upload.filename == "photo.JPG"
    assert upload.extension == "JPG"
    assert upload.content_type == "text/plain"
