"""Integration (doc 16) — the s3 disk round-trips against a real S3-compatible store (RustFS)."""

from __future__ import annotations

import os
import uuid
from datetime import timedelta
from typing import Any

import httpx
import pytest

from arvel.dates import Date
from arvel.filesystem import FilesystemManager, Visibility

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


@pytest.fixture
async def s3_disk(rustfs_s3: dict[str, str], configure_app: Any) -> Any:
    """A fresh bucket + s3 disk on the RustFS container, per test."""
    from anyio import to_thread

    bucket = f"arvel-{uuid.uuid4().hex[:10]}"
    app = configure_app(filesystems={"disks": {"s3": {**rustfs_s3, "bucket": bucket}}})
    disk = FilesystemManager(app).disk("s3")
    await to_thread.run_sync(disk.fs.mkdir, bucket)
    return disk


async def test_metadata_size_mtime_mime_missing(s3_disk: Any) -> None:
    await s3_disk.put("reports/q1.csv", b"a,b,c\n1,2,3\n")

    assert await s3_disk.size("reports/q1.csv") == len(b"a,b,c\n1,2,3\n")
    assert await s3_disk.mime_type("reports/q1.csv") == "text/csv"
    assert await s3_disk.missing("reports/q1.csv") is False
    assert await s3_disk.missing("reports/nope.csv") is True

    modified = await s3_disk.last_modified("reports/q1.csv")
    assert isinstance(modified, Date)
    assert abs(modified.to_py().timestamp() - Date.now().to_py().timestamp()) < 120


async def test_copy_move_and_list(s3_disk: Any) -> None:
    await s3_disk.put("a.txt", b"1")
    await s3_disk.put("docs/b.txt", b"2")
    await s3_disk.put("docs/sub/c.txt", b"3")

    await s3_disk.copy("a.txt", "copies/a-copy.txt")
    assert await s3_disk.get("copies/a-copy.txt") == b"1"
    assert await s3_disk.exists("a.txt") is True  # copy keeps the source

    await s3_disk.move("a.txt", "moved/a.txt")
    assert await s3_disk.get("moved/a.txt") == b"1"
    assert await s3_disk.exists("a.txt") is False  # move removes the source

    all_files = sorted(await s3_disk.all_files(""))
    assert "docs/b.txt" in all_files
    assert "docs/sub/c.txt" in all_files
    assert "moved/a.txt" in all_files
    assert sorted(await s3_disk.all_directories("")) == ["copies", "docs", "docs/sub", "moved"]
    assert await s3_disk.files("docs") == ["docs/b.txt"]


async def test_visibility_dispatches_the_canned_acl(s3_disk: Any) -> None:
    """``set_visibility``/``get_visibility`` call the standard S3 canned-ACL API
    (``put_object_acl``/``get_object_acl`` via s3fs ``chmod``) without error, and
    ``get_visibility`` always returns a real ``Visibility`` member.

    RustFS accepts the canned ACL (``put_object_acl`` returns 200) but — verified directly
    against the container — its ``get_object_acl`` always reports only the owner's
    ``FULL_CONTROL`` grant, never an ``AllUsers`` grant, so a public/private round-trip can't be
    observed against *this* backend; a raw anonymous GET returns 403 regardless of the ACL
    applied. That enforcement gap is RustFS's, not this driver's — the same calls apply the real
    ``public-read``/``private`` canned ACL on AWS S3 and other ACL-honoring S3-compatible stores.
    The always-enforced 403-then-200 behavior (private by default; ``temporary_url`` grants
    access) is covered in :func:`test_temporary_url_grants_time_boxed_access`.
    """
    await s3_disk.put("a.txt", b"content")

    await s3_disk.set_visibility("a.txt", Visibility.PUBLIC)
    assert isinstance(await s3_disk.get_visibility("a.txt"), Visibility)

    await s3_disk.set_visibility("a.txt", Visibility.PRIVATE)
    assert isinstance(await s3_disk.get_visibility("a.txt"), Visibility)


async def test_temporary_url_grants_time_boxed_access(s3_disk: Any) -> None:
    """A fresh object is private by RustFS's default (no public bucket/object policy) — its raw,
    unsigned URL 403s — while ``temporary_url`` presigns the request (SigV4 query auth, verified
    independently of any object ACL) and reaches it. This is the genuinely observable half of the
    AC on this backend (see the ACL-fidelity note on ``test_visibility_dispatches_the_canned_acl``
    for why the ACL-driven public/private split itself isn't observable against RustFS)."""
    await s3_disk.put("private.txt", b"secret content")

    async with httpx.AsyncClient() as client:
        raw_response = await client.get(s3_disk.url("private.txt"))
        assert raw_response.status_code == 403

        signed = await s3_disk.temporary_url("private.txt", timedelta(minutes=5))
        signed_response = await client.get(signed)
        assert signed_response.status_code == 200
        assert signed_response.content == b"secret content"


async def test_streams_a_large_object(s3_disk: Any) -> None:
    payload = os.urandom(11 * 1024 * 1024)  # > 10 MiB
    assert len(payload) > 10 * 1024 * 1024

    async def _source() -> Any:
        step = 1024 * 1024
        for offset in range(0, len(payload), step):
            yield payload[offset : offset + step]

    await s3_disk.write_stream("big.bin", _source())
    assert await s3_disk.size("big.bin") == len(payload)

    chunks = [chunk async for chunk in s3_disk.read_stream("big.bin", chunk_size=1024 * 1024)]
    assert len(chunks) > 1
    assert b"".join(chunks) == payload
