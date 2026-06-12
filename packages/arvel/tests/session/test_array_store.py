"""Array session store behavior."""

from __future__ import annotations

import pytest
from arvel.session.stores.array import ArraySessionStore


async def test_array_session_store_roundtrip_and_destroy() -> None:
    store = ArraySessionStore()

    assert await store.read("missing") == {}

    await store.write("sid", {"user_id": "1"})
    first = await store.read("sid")
    first["user_id"] = "mutated"
    assert await store.read("sid") == {"user_id": "1"}

    await store.destroy("sid")
    assert await store.read("sid") == {}


async def test_array_session_store_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    store = ArraySessionStore(lifetime=1)

    monkeypatch.setattr("time.time", lambda: 1000.0)
    await store.write("expired", {"stale": True})
    monkeypatch.setattr("time.time", lambda: 1002.0)

    assert await store.read("expired") == {}


async def test_array_session_store_gc_removes_expired_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ArraySessionStore(lifetime=1)

    monkeypatch.setattr("time.time", lambda: 1000.0)
    await store.write("drop", {"ok": False})
    monkeypatch.setattr("time.time", lambda: 1002.0)

    assert await store.gc(max_lifetime=7200) == 1
    assert await store.read("drop") == {}


async def test_array_session_store_zero_lifetime_never_expires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ArraySessionStore(lifetime=0)

    monkeypatch.setattr("time.time", lambda: 1000.0)
    await store.write("keep", {"ok": True})
    monkeypatch.setattr("time.time", lambda: 99999.0)

    assert await store.gc(max_lifetime=7200) == 0
    assert await store.read("keep") == {"ok": True}
