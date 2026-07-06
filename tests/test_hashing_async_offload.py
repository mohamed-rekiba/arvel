"""The hashing seam offloads to a worker thread but produces identical results (round H3a)."""

from __future__ import annotations

import pytest

from arvel.security.hashing import HashManager


@pytest.mark.asyncio
async def test_make_async_check_async_roundtrip() -> None:
    hm = HashManager("argon2id")
    hashed = await hm.make_async("s3cret")
    assert await hm.check_async("s3cret", hashed) is True
    assert await hm.check_async("wrong", hashed) is False


@pytest.mark.asyncio
async def test_async_seam_is_consistent_with_sync() -> None:
    hm = HashManager("argon2id")
    hashed = await hm.make_async("pw")
    # a hash made off-loop verifies through the sync path and vice versa
    assert hm.check("pw", hashed) is True
    assert await hm.check_async("pw", hm.make("pw")) is True
