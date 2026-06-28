"""Auth — email verification (Laravel MustVerifyEmail parity): a real persisted User carries
``email_verified_at``; ``has_verified_email()`` / ``mark_email_as_verified()`` drive it, and the
``verified`` route middleware honors it on that real user (not just a hand-rolled fake)."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
import sqlalchemy as sa

from arvel import Model
from arvel.auth import Authenticatable, current_user
from arvel.auth.middleware import EnsureEmailVerified
from arvel.database import ConnectionResolver
from arvel.http.exceptions import HttpException


class VerifyUser(Authenticatable, Model):
    __table_name__ = "verify_users"
    __fields__: ClassVar[dict[str, Any]] = {"email": str, "email_verified_at": "datetime"}
    __fillable__: ClassVar[list[str]] = ["email"]
    __casts__: ClassVar[dict[str, Any]] = {"email_verified_at": "datetime"}


async def _db() -> ConnectionResolver:
    db = ConnectionResolver()
    VerifyUser.set_connection(db)
    await db.execute(sa.schema.CreateTable(VerifyUser.__table__))
    return db


async def _call_next(_request: Any) -> str:
    return "OK"


async def test_mark_and_check_verified_persist() -> None:
    db = await _db()
    try:
        user = await VerifyUser.create(email="a@b.com")
        assert user.has_verified_email() is False  # email_verified_at is None on a fresh user

        first = await user.mark_email_as_verified()
        assert first is True
        assert user.has_verified_email() is True
        assert await user.mark_email_as_verified() is False  # already verified → no-op

        fetched = await VerifyUser.find(user.id)  # persisted across a fresh fetch
        assert fetched.has_verified_email() is True

        await fetched.mark_email_as_unverified()
        assert fetched.has_verified_email() is False
        assert (await VerifyUser.find(user.id)).has_verified_email() is False
    finally:
        await db.dispose()


async def test_email_for_verification() -> None:
    db = await _db()
    try:
        user = await VerifyUser.create(email="who@example.com")
        assert user.email_for_verification() == "who@example.com"
    finally:
        await db.dispose()


async def test_verified_middleware_honors_a_real_user() -> None:
    db = await _db()
    try:
        user = await VerifyUser.create(email="c@d.com")
        token = current_user.set(user)
        try:
            with pytest.raises(HttpException):  # unverified → 403
                await EnsureEmailVerified().handle(object(), _call_next)
            await user.mark_email_as_verified()
            assert (
                await EnsureEmailVerified().handle(object(), _call_next) == "OK"
            )  # verified → passes
        finally:
            current_user.reset(token)
    finally:
        await db.dispose()
