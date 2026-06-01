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
        await store.write(session_id, data, lifetime=120)
        # Read back using the same store (simulates next request cookie)
        cookie_value = store.last_written_cookie
        read_data = await store.read_from_cookie(cookie_value)
        assert read_data["user_id"] == 42

    @pytest.mark.asyncio
    async def test_tampered_cookie_returns_empty_session(self, store: CookieStore) -> None:
        session_id = "tamper-me"
        await store.write(session_id, {"secret": "data"}, lifetime=120)
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

        await store1.write("s1", {"user": 1}, lifetime=120)
        cookie = store1.last_written_cookie
        result = await store2.read_from_cookie(cookie)
        assert result == {}

    @pytest.mark.asyncio
    async def test_payload_is_not_plaintext(self, store: CookieStore) -> None:
        await store.write("s", {"secret_data": "top_secret"}, lifetime=120)
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
