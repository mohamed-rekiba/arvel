"""Tests for Session File Store — FR-006-021."""

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
        await store.write("sid1", {"user_id": 7}, lifetime=120)
        data = await store.read("sid1")
        assert data["user_id"] == 7

    @pytest.mark.asyncio
    async def test_missing_session_returns_empty(self, store: FileSessionStore) -> None:
        assert await store.read("nonexistent") == {}

    @pytest.mark.asyncio
    async def test_file_created_per_session(self, store: FileSessionStore, tmp_path: Path) -> None:
        await store.write("sid2", {"k": "v"}, lifetime=120)
        session_files = list(tmp_path.glob("*.session"))
        assert len(session_files) >= 1

    @pytest.mark.asyncio
    async def test_destroy_removes_file(self, store: FileSessionStore, tmp_path: Path) -> None:
        await store.write("sid3", {"k": "v"}, lifetime=120)
        await store.destroy("sid3")
        assert await store.read("sid3") == {}

    @pytest.mark.asyncio
    async def test_gc_removes_expired_sessions(
        self, store: FileSessionStore, tmp_path: Path
    ) -> None:
        await store.write("old", {"k": "v"}, lifetime=1)
        # Backdate the file mtime
        session_file = tmp_path / "old.session"
        if session_file.exists():
            import os

            os.utime(session_file, (0, 0))

        deleted = await store.gc(max_lifetime=120)
        assert deleted >= 1
