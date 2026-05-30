"""Array session store behavior."""

from __future__ import annotations

import pytest
from arvel.session.stores.array import ArraySessionStore


async def test_array_session_store_roundtrip_and_destroy() -> None:
    store = ArraySessionStore()

    assert await store.read("missing") == {}

    await store.write("sid", {"user_id": "1"}, lifetime=7200)
    first = await store.read("sid")
    first["user_id"] = "mutated"
    assert await store.read("sid") == {"user_id": "1"}

    await store.destroy("sid")
    assert await store.read("sid") == {}


async def test_array_session_store_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    store = ArraySessionStore()

    monkeypatch.setattr("time.time", lambda: 1000.0)
    await store.write("expired", {"stale": True}, lifetime=1)
    monkeypatch.setattr("time.time", lambda: 1002.0)

    assert await store.read("expired") == {}


async def test_array_session_store_gc_removes_expired_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ArraySessionStore()

    monkeypatch.setattr("time.time", lambda: 1000.0)
    await store.write("keep", {"ok": True}, lifetime=0)
    await store.write("drop", {"ok": False}, lifetime=1)
    monkeypatch.setattr("time.time", lambda: 1002.0)

    assert await store.gc(max_lifetime=7200) == 1
    assert await store.read("keep") == {"ok": True}
    assert await store.read("drop") == {}
    assert store.lifetime == 7200
