"""Eloquent-parity (backlog 006, S2): hashed cast, force_fill, unguarded()."""

from __future__ import annotations

from typing import ClassVar

import pytest
from arvel.database import Model
from arvel.database.exceptions import MassAssignmentError
from arvel.facades.hash import Hash
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class Account(Model):
    __tablename__ = "accounts_h"
    __casts__: ClassVar[dict[str, str]] = {"password": "hashed"}
    __fillable__: ClassVar[list[str] | None] = ["email"]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    email: Mapped[str] = mapped_column(String(120), nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False, default="")


async def _create_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def test_hashed_cast_hashes_on_write(engine: AsyncEngine, session: AsyncSession) -> None:
    await _create_tables(engine)
    acct = Account(email="a@x.io", password="secret")
    assert acct.password != "secret"
    assert Hash.check("secret", acct.password) is True


async def test_hashed_cast_passes_through_existing_hash(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _create_tables(engine)
    digest = Hash.make("secret")
    acct = Account(email="b@x.io", password=digest)
    # Already hashed → must not be re-hashed (idempotent).
    assert acct.password == digest


async def test_hashed_cast_not_rehashed_on_read_roundtrip(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _create_tables(engine)
    acct = Account(email="c@x.io", password="hunter2")
    await acct.save()
    stored = acct.password
    fresh = await Account.where(email="c@x.io").first()
    assert fresh is not None
    assert fresh.password == stored
    assert Hash.check("hunter2", fresh.password) is True


async def test_force_fill_bypasses_guards(engine: AsyncEngine, session: AsyncSession) -> None:
    await _create_tables(engine)
    acct = Account(email="d@x.io")
    # `password` is not in __fillable__ → normal fill would reject it.
    with pytest.raises(MassAssignmentError):
        acct.fill(password="nope")
    acct.force_fill(email="d@x.io", password="forced")
    assert Hash.check("forced", acct.password) is True


async def test_unguarded_suspends_mass_assignment(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _create_tables(engine)
    with Account.unguarded():
        acct = await Account.create(email="e@x.io", password="open")
    assert acct.id is not None
    # Guards restored after the block.
    with pytest.raises(MassAssignmentError):
        await Account.create(email="f@x.io", password="blocked")


async def test_unguarded_is_reentrant(engine: AsyncEngine, session: AsyncSession) -> None:
    await _create_tables(engine)
    with Account.unguarded():
        with Account.unguarded():
            Account(email="g@x.io").fill(password="inner")
        # Still suspended after the inner block.
        Account(email="h@x.io").fill(password="outer")
    # Restored after outermost.
    with pytest.raises(MassAssignmentError):
        Account(email="i@x.io").fill(password="blocked")
