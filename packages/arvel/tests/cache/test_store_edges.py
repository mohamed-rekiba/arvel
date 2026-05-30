"""Cache store edge behavior."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from arvel.cache.exceptions import TagsNotSupported
from arvel.cache.stores.array import ArrayStore
from arvel.cache.stores.file import FileStore
from arvel.cache.stores.null import NullStore


async def test_array_store_expiry_many_put_many_and_gc(monkeypatch: pytest.MonkeyPatch) -> None:
    store = ArrayStore(prefix="test")

    monkeypatch.setattr("time.monotonic", lambda: 1000.0)
    await store.put("expired", "old", ttl=1)
    await store.put_many({"a": 1, "b": 2})
    monkeypatch.setattr("time.monotonic", lambda: 1002.0)

    assert await store.get("expired", "fallback") == "fallback"
    assert await store.has("expired") is False
    assert await store.many(["a", "b", "missing"]) == {"a": 1, "b": 2, "missing": None}
    assert await store.forget("missing") is False
    assert await store.gc() == 0


async def test_array_store_gc_removes_stale_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    store = ArrayStore(prefix="test")

    monkeypatch.setattr("time.monotonic", lambda: 1000.0)
    await store.put("stale", "old", ttl=1)
    monkeypatch.setattr("time.monotonic", lambda: 1002.0)

    assert await store.gc() == 1


async def test_file_store_expiry_corrupt_files_and_tags(tmp_path: Path) -> None:
    store = FileStore(tmp_path, prefix="test")

    await store.put("valid", {"ok": True})
    await store.put("expired", "old", ttl=-1)
    file_for = cast("Callable[[str], Path]", object.__getattribute__(store, "_file_for"))
    corrupt = file_for("corrupt")
    corrupt.write_text("{not-json")

    assert await store.get("valid") == {"ok": True}
    assert await store.has("valid") is True
    assert await store.get("expired", "fallback") == "fallback"
    assert await store.has("expired") is False
    assert await store.get("corrupt", "fallback") == "fallback"
    assert await store.has("corrupt") is False
    await store.put_many({"a": 1, "b": 2})
    assert await store.many(["a", "b"]) == {"a": 1, "b": 2}
    assert await store.forget("missing") is False
    await store.flush()
    assert list(tmp_path.glob("*.json")) == []

    with pytest.raises(TagsNotSupported):
        store.tags(["tenant"])


async def test_file_store_handles_payload_missing_expiry(tmp_path: Path) -> None:
    store = FileStore(tmp_path, prefix="test")
    file_for = cast("Callable[[str], Path]", object.__getattribute__(store, "_file_for"))
    file_for("legacy").write_text(json.dumps({"value": "legacy"}))

    assert await store.get("legacy") == "legacy"


async def test_null_store_discards_everything() -> None:
    store = NullStore()

    await store.put("key", "value")
    await store.forever("forever", "value")
    await store.put_many({"a": 1})
    await store.flush()

    assert await store.get("key", "fallback") == "fallback"
    assert await store.forget("key") is False
    assert await store.has("key") is False
    assert await store.many(["a", "b"]) == {"a": None, "b": None}
    with pytest.raises(TagsNotSupported):
        store.tags(["tenant"])
