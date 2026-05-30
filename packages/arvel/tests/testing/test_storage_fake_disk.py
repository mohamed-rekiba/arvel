"""Storage fake disk behavior."""

from __future__ import annotations

from io import BytesIO

import pytest
from arvel.testing.fakes.storage import StorageFake, StorageFakeContext


async def test_storage_fake_memory_disk_roundtrip() -> None:
    fake = StorageFake()
    disk = fake.disk("avatars")

    assert await disk.exists("a.txt") is False
    await disk.put("a.txt", "hello")
    await disk.put("nested/b.bin", BytesIO(b"bytes"))

    assert await disk.exists("a.txt") is True
    assert await disk.get("a.txt") == b"hello"
    assert await disk.get("nested/b.bin") == b"bytes"
    assert await disk.size("nested/b.bin") == 5
    assert disk.url("a.txt") == "memory:///a.txt"
    assert disk.temporary_url("a.txt", 60) == "memory:///a.txt?tmp=1&expiry=60"
    assert await disk.list() == ["a.txt", "nested/b.bin"]
    assert await disk.list("nested") == ["nested/b.bin"]
    assert [path async for path in disk.files_in("nested")] == ["nested/b.bin"]
    assert fake.has_path("a.txt", "avatars") is True
    assert await disk.delete("a.txt") is True
    assert await disk.delete("missing.txt") is False


async def test_storage_fake_missing_file_raises() -> None:
    disk = StorageFake().disk()

    with pytest.raises(FileNotFoundError, match="missing.txt"):
        await disk.get("missing.txt")


def test_storage_fake_context_exposes_named_disk() -> None:
    context = StorageFakeContext()
    assert context.disk("local") is context.fake.disk("local")
