"""Auth (doc 15) — rotating refresh tokens."""

from __future__ import annotations

import asyncio

import sqlalchemy as sa

from arvel.auth.refresh import (
    RefreshToken,
    issue_refresh_token,
    revoke_all_refresh_tokens,
    rotate_refresh_token,
)
from arvel.database import ConnectionResolver


async def _db() -> ConnectionResolver:
    db = ConnectionResolver()
    RefreshToken.set_connection(db)
    await db.execute(sa.schema.CreateTable(RefreshToken.__table__))
    return db


async def test_issue_then_rotate_returns_new_token() -> None:
    db = await _db()
    try:
        original = await issue_refresh_token(42)
        result = await rotate_refresh_token(original)
        assert result is not None
        new_token, user_id = result
        assert user_id == 42
        assert new_token != original
    finally:
        await db.dispose()


async def test_rotated_token_is_single_use() -> None:
    db = await _db()
    try:
        original = await issue_refresh_token(7)
        await rotate_refresh_token(original)  # revokes `original`
        assert await rotate_refresh_token(original) is None  # cannot reuse
    finally:
        await db.dispose()


async def test_unknown_token_rejected() -> None:
    db = await _db()
    try:
        assert await rotate_refresh_token("never-issued") is None
    finally:
        await db.dispose()


# --- reuse detection / family revocation (DR-0014) ----------------------------


async def test_reuse_of_rotated_token_revokes_the_whole_family() -> None:
    db = await _db()
    try:
        a = await issue_refresh_token(99)
        rotated = await rotate_refresh_token(a)  # a revoked, b issued
        assert rotated is not None
        b, _ = rotated

        # An attacker replays the old token `a` → theft signal.
        assert await rotate_refresh_token(a) is None
        # The legitimate client's current token `b` is now dead too — forced re-login.
        assert await rotate_refresh_token(b) is None
        # Every refresh row for user 99 is revoked.
        rows = await RefreshToken.where(tokenable_id=99).get()
        assert rows and all(row.revoked for row in rows)
    finally:
        await db.dispose()


async def test_family_revocation_is_scoped_to_the_user() -> None:
    db = await _db()
    try:
        a = await issue_refresh_token(1)
        other = await issue_refresh_token(2)  # a different user — must stay valid
        await rotate_refresh_token(a)  # a revoked, b issued for user 1
        await rotate_refresh_token(a)  # reuse → revoke user 1's family

        # User 2 is untouched and can still rotate.
        assert await rotate_refresh_token(other) is not None
    finally:
        await db.dispose()


async def test_revoke_all_refresh_tokens_helper() -> None:
    db = await _db()
    try:
        await issue_refresh_token(5)
        await issue_refresh_token(5)
        await revoke_all_refresh_tokens(5)
        rows = await RefreshToken.where(tokenable_id=5).get()
        assert rows and all(row.revoked for row in rows)
    finally:
        await db.dispose()


async def test_double_rotation_mints_exactly_one_successor() -> None:
    """TOCTOU: two rotations of the SAME token must not both succeed — the atomic conditional update
    lets exactly one win; the other trips reuse detection (and revokes the family)."""
    db = await _db()
    try:
        original = await issue_refresh_token(42)
        r1, r2 = await asyncio.gather(
            rotate_refresh_token(original), rotate_refresh_token(original)
        )
        winners = [r for r in (r1, r2) if r is not None]
        assert len(winners) == 1  # exactly one new token minted from the one presented token

        # the loser hit the reuse path → user 42's family was revoked, so the winner's token is dead too
        assert await rotate_refresh_token(winners[0][0]) is None
    finally:
        await db.dispose()
