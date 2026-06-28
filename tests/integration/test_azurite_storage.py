"""Integration (doc 16/20) — the azure disk round-trips against the Azurite blob emulator."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from arvel.filesystem import FilesystemManager

pytestmark = pytest.mark.integration


async def test_azure_disk_roundtrip_on_azurite(azurite_conn: str, configure_app: Any) -> None:
    from anyio import to_thread

    container = f"arvel-{uuid.uuid4().hex[:10]}"
    app = configure_app(
        filesystems={
            "disks": {"azure": {"connection_string": azurite_conn, "container": container}}
        }
    )
    disk = FilesystemManager(app).disk("azure")

    await to_thread.run_sync(disk.fs.mkdir, container)  # create the blob container

    path = await disk.put("docs/readme.txt", b"hello azure")
    assert path == f"{container}/docs/readme.txt"
    assert await disk.exists("docs/readme.txt") is True
    assert await disk.get("docs/readme.txt") == b"hello azure"

    await disk.delete("docs/readme.txt")
    assert await disk.exists("docs/readme.txt") is False
