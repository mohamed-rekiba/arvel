"""Integration (doc 16) — the s3 disk round-trips against a real S3-compatible store (RustFS)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from arvel.filesystem import FilesystemManager

pytestmark = pytest.mark.integration


async def test_s3_disk_roundtrip_on_rustfs(rustfs_s3: dict[str, str], configure_app: Any) -> None:
    from anyio import to_thread

    bucket = f"arvel-{uuid.uuid4().hex[:10]}"
    app = configure_app(filesystems={"disks": {"s3": {**rustfs_s3, "bucket": bucket}}})
    disk = FilesystemManager(app).disk("s3")

    await to_thread.run_sync(disk.fs.mkdir, bucket)  # create the bucket on RustFS

    path = await disk.put("docs/readme.txt", b"hello s3")
    assert path == f"{bucket}/docs/readme.txt"
    assert await disk.exists("docs/readme.txt") is True
    assert await disk.get("docs/readme.txt") == b"hello s3"

    await disk.delete("docs/readme.txt")
    assert await disk.exists("docs/readme.txt") is False
