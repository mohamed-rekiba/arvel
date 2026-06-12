"""Tests for CookieStore — (cookie security)."""

from __future__ import annotations

import base64
import os
from typing import Any

import pytest
from arvel.session.stores.cookie import CookieStore


@pytest.fixture
def app_key() -> bytes:
    return os.urandom(32)


@pytest.fixture
def store(app_key: bytes) -> CookieStore:
    return CookieStore(app_key=app_key, lifetime=120)


class TestCookieStoreEncryption:
    @pytest.mark.asyncio
    async def test_write_and_read_roundtrip(self, store: CookieStore) -> None:
        session_id = "test-session-id"
        data: dict[str, Any] = {"user_id": 42, "name": "Alice"}
        await store.write(session_id, data)
        # Read back using the same store (simulates next request cookie)
        cookie_value = store.last_written_cookie
        read_data = await store.read_from_cookie(cookie_value)
        assert read_data["user_id"] == 42

    @pytest.mark.asyncio
    async def test_tampered_cookie_returns_empty_session(self, store: CookieStore) -> None:
        session_id = "tamper-me"
        await store.write(session_id, {"secret": "data"})
        tampered = "garbage_not_valid_base64_aead"
        result = await store.read_from_cookie(tampered)
        assert result == {}

    @pytest.mark.asyncio
    async def test_missing_session_cookie_returns_empty(self, store: CookieStore) -> None:
        result = await store.read("")
        assert result == {}

    @pytest.mark.asyncio
    async def test_different_keys_cannot_decrypt(self, app_key: bytes) -> None:
        store1 = CookieStore(app_key=app_key, lifetime=120)
        store2 = CookieStore(app_key=os.urandom(32), lifetime=120)

        await store1.write("s1", {"user": 1})
        cookie = store1.last_written_cookie
        result = await store2.read_from_cookie(cookie)
        assert result == {}

    @pytest.mark.asyncio
    async def test_payload_is_not_plaintext(self, store: CookieStore) -> None:
        await store.write("s", {"secret_data": "top_secret"})
        cookie = store.last_written_cookie
        # The raw cookie value must not contain the plaintext key
        try:
            raw = base64.b64decode(cookie.encode())
        except Exception:
            raw = cookie.encode()
        assert b"top_secret" not in raw

    @pytest.mark.asyncio
    async def test_destroy_is_noop_for_cookie_store(self, store: CookieStore) -> None:
        await store.destroy("any_session_id")  # should not raise

    @pytest.mark.asyncio
    async def test_expired_cookie_reads_as_empty(
        self, store: CookieStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A replayed cookie past its lifetime must decrypt to {} — the browser's
        # Max-Age can't be trusted, so the server enforces the embedded expiry.
        # cookie.py does `import time`, so patching the stdlib module hits it too.
        import time

        await store.write("s", {"user_id": 7})
        cookie = store.last_written_cookie
        # Capture now before patching to avoid the fake recursing into itself.
        future = time.time() + 3600
        monkeypatch.setattr(time, "time", lambda: future)
        assert await store.read_from_cookie(cookie) == {}

    @pytest.mark.asyncio
    async def test_unexpired_cookie_still_reads(self, store: CookieStore) -> None:
        await store.write("s", {"user_id": 7})
        cookie = store.last_written_cookie
        assert (await store.read_from_cookie(cookie))["user_id"] == 7

    @pytest.mark.asyncio
    async def test_zero_lifetime_never_expires(self, app_key: bytes) -> None:
        # lifetime <= 0 means no embedded expiry — the cookie stays readable.
        forever = CookieStore(app_key=app_key, lifetime=0)
        await forever.write("s", {"user_id": 7})
        assert (await forever.read_from_cookie(forever.last_written_cookie))["user_id"] == 7
