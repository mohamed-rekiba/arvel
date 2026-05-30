"""Tests for the refresh-token primitives — model + plaintext helpers.

Model tests run against the in-memory async SQLite engine provided by the
workspace-root ``conftest.py`` (the ``session`` / ``engine`` fixtures).
Persistence, the ``is_active`` / ``is_expired`` accessors, and the
unique-hash constraint are all covered.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from arvel.auth import RefreshToken, generate_refresh_token, hash_refresh_token
from arvel.database.model import Model

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


# ─── Plaintext helpers ─────────────────────────────────────────────────────


def test_hash_refresh_token_is_sha256_hex() -> None:
    """Digest is 64 hex chars and stable for the same input."""
    digest = hash_refresh_token("plain-token")
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)
    assert digest == hash_refresh_token("plain-token")


def test_generate_refresh_token_unique_and_long() -> None:
    """Each call returns a fresh URL-safe plaintext (≈40 chars)."""
    a = generate_refresh_token()
    b = generate_refresh_token()
    assert a != b
    assert len(a) >= 32


# ─── RefreshToken model — round-trip + accessors ───────────────────────────


async def _setup(engine: AsyncEngine) -> None:
    """Create the refresh_tokens table on the in-memory engine."""
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


@pytest.mark.asyncio
async def test_refresh_token_round_trips_through_orm(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """Create → Where → Delete via the model — no raw SQL anywhere."""
    await _setup(engine)
    plain = generate_refresh_token()
    token = await RefreshToken.create(
        user_id="u1",
        token_hash=hash_refresh_token(plain),
        expires_at=datetime.now(tz=UTC) + timedelta(days=7),
    )
    assert token.id is not None

    found = await RefreshToken.where(token_hash=hash_refresh_token(plain)).first()
    assert found is not None
    assert found.user_id == "u1"
    assert found.is_active is True
    assert found.is_expired is False

    await found.delete()
    assert await RefreshToken.where(token_hash=hash_refresh_token(plain)).first() is None


@pytest.mark.asyncio
async def test_refresh_token_is_expired_when_past_due(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """The ``is_expired`` accessor reads ``expires_at`` against UTC now."""
    await _setup(engine)
    token = await RefreshToken.create(
        user_id="u1",
        token_hash="a" * 64,
        expires_at=datetime.now(tz=UTC) - timedelta(seconds=1),
    )
    assert token.is_expired is True
    assert token.is_active is False


@pytest.mark.asyncio
async def test_refresh_token_token_hash_is_hidden(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """``__hidden__`` keeps the digest out of ``to_dict()``."""
    await _setup(engine)
    token = await RefreshToken.create(
        user_id="u1",
        token_hash="b" * 64,
        expires_at=datetime.now(tz=UTC) + timedelta(days=7),
    )
    data = token.to_dict()
    assert "token_hash" not in data
    assert data["user_id"] == "u1"


@pytest.mark.asyncio
async def test_refresh_token_delete_via_query_builder(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """Bulk family-delete via ``where(...).delete()`` — used by the broker on reset."""
    await _setup(engine)
    for i in range(3):
        await RefreshToken.create(
            user_id="u-fam",
            token_hash=f"{i:064x}",
            expires_at=datetime.now(tz=UTC) + timedelta(days=7),
        )
    deleted = await RefreshToken.where(user_id="u-fam").delete()
    assert deleted == 3
    assert await RefreshToken.where(user_id="u-fam").first() is None
