"""Tests for Session File Store."""

from __future__ import annotations

from pathlib import Path

import pytest
from arvel.session.stores.file import FileSessionStore


@pytest.fixture
def store(tmp_path: Path) -> FileSessionStore:
    return FileSessionStore(path=tmp_path, lifetime=120)


class TestFileSessionStore:
    @pytest.mark.asyncio
    async def test_read_write_roundtrip(self, store: FileSessionStore) -> None:
        await store.write("sid1", {"user_id": 7})
        data = await store.read("sid1")
        assert data["user_id"] == 7

    @pytest.mark.asyncio
    async def test_missing_session_returns_empty(self, store: FileSessionStore) -> None:
        assert await store.read("nonexistent") == {}

    @pytest.mark.asyncio
    async def test_file_created_per_session(self, store: FileSessionStore, tmp_path: Path) -> None:
        await store.write("sid2", {"k": "v"})
        session_files = list(tmp_path.glob("*.session"))
        assert len(session_files) >= 1

    @pytest.mark.asyncio
    async def test_destroy_removes_file(self, store: FileSessionStore, tmp_path: Path) -> None:
        await store.write("sid3", {"k": "v"})
        await store.destroy("sid3")
        assert await store.read("sid3") == {}

    @pytest.mark.asyncio
    async def test_gc_removes_expired_sessions(
        self, store: FileSessionStore, tmp_path: Path
    ) -> None:
        await store.write("old", {"k": "v"})
        # Backdate the file mtime. The on-disk name is hashed, so glob for it.
        import os

        for session_file in tmp_path.glob("*.session"):
            os.utime(session_file, (0, 0))

        deleted = await store.gc(max_lifetime=120)
        assert deleted >= 1

    @pytest.mark.asyncio
    async def test_expired_file_reads_as_empty(
        self, store: FileSessionStore, tmp_path: Path
    ) -> None:
        """A stale file is treated as empty on read, before GC ever runs."""
        import os

        await store.write("stale", {"k": "v"})
        for session_file in tmp_path.glob("*.session"):
            os.utime(session_file, (0, 0))
        assert await store.read("stale") == {}

    @pytest.mark.asyncio
    async def test_traversal_id_does_not_escape_session_dir(
        self, store: FileSessionStore, tmp_path: Path
    ) -> None:
        """A tampered cookie id with ../ must stay inside the session dir."""
        outside = tmp_path.parent / "escaped.session"
        await store.write("../escaped", {"pwned": True})
        assert not outside.exists()
        # The hashed name lands inside the configured dir and round-trips.
        assert await store.read("../escaped") == {"pwned": True}
        assert list(tmp_path.glob("*.session"))
