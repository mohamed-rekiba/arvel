"""FR-028-13, FR-028-15, FR-028-26 — RefreshToken model rotation behaviour.

These exercise the model invariants the broker depends on directly — no
fakes, no broker, just the ORM. Pairs with the broker integration tests
in ``test_broker.py`` which exercise the full rotation flow.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from arvel.auth import RefreshToken, hash_refresh_token
from arvel.database.model import Model

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


@pytest.fixture
async def setup_db(engine: AsyncEngine, session: AsyncSession) -> AsyncSession:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    return session


@pytest.mark.asyncio
async def test_rotate_replaces_old_row_atomically_via_orm(
    setup_db: AsyncSession,
) -> None:
    """FR-028-13 — rotation = ``where(token_hash=h).delete()`` + ``.create(...)``."""
    h_old = hash_refresh_token("old-plain")
    await RefreshToken.create(
        user_id="1",
        token_hash=h_old,
        expires_at=datetime.now(tz=UTC) + timedelta(days=14),
    )

    found = await RefreshToken.where(token_hash=h_old).first()
    assert found is not None
    await found.delete()

    h_new = hash_refresh_token("new-plain")
    await RefreshToken.create(
        user_id="1",
        token_hash=h_new,
        expires_at=datetime.now(tz=UTC) + timedelta(days=14),
    )

    assert await RefreshToken.where(token_hash=h_old).first() is None
    assert await RefreshToken.where(token_hash=h_new).first() is not None


@pytest.mark.asyncio
async def test_delete_family_revokes_every_token_for_user(
    setup_db: AsyncSession,
) -> None:
    """FR-028-26 — ``where(user_id=u).delete()`` revokes every active row."""
    for i in range(3):
        await RefreshToken.create(
            user_id="42",
            token_hash=f"{i:064x}",
            expires_at=datetime.now(tz=UTC) + timedelta(days=14),
        )
    deleted = await RefreshToken.where(user_id="42").delete()
    assert deleted == 3
    assert await RefreshToken.where(user_id="42").first() is None


@pytest.mark.asyncio
async def test_find_returns_none_for_unknown_hash(setup_db: AsyncSession) -> None:
    """No-row case is the broker's signal to raise InvalidCredentialsError."""
    assert await RefreshToken.where(token_hash="z" * 64).first() is None


@pytest.mark.asyncio
async def test_unique_constraint_prevents_duplicate_hash(
    setup_db: AsyncSession,
) -> None:
    """FR-028-13 invariant — UNIQUE(token_hash) blocks INSERT of a clashing digest."""
    from sqlalchemy.exc import IntegrityError

    digest = hash_refresh_token("plain-1")
    await RefreshToken.create(
        user_id="1",
        token_hash=digest,
        expires_at=datetime.now(tz=UTC) + timedelta(days=14),
    )
    with pytest.raises(IntegrityError):
        await RefreshToken.create(
            user_id="2",
            token_hash=digest,
            expires_at=datetime.now(tz=UTC) + timedelta(days=14),
        )
