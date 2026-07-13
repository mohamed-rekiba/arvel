"""14 AUTH-SESSION — the password_reset_tokens table + PasswordBroker, against a real PostgreSQL
(not just SQLite — the framework migration + the model must agree on a real dialect)."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.auth.password_reset import PasswordBroker, PasswordResetStatus, PasswordResetToken
from arvel.auth.remember import RememberToken
from arvel.database import ConnectionResolver

pytestmark = pytest.mark.integration


class _RecordingDispatcher:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def dispatch(self, event: Any) -> list[Any]:
        self.events.append(event)
        return []


class _User:
    def __init__(self, uid: int, email: str) -> None:
        self.id = uid
        self.email = email
        self.password = "old-hash"

    def get_auth_identifier(self) -> int:
        return self.id


def _set_password(user: _User, new_password: str) -> None:
    user.password = f"hash({new_password})"


async def test_full_password_reset_round_trip_on_postgres(postgres_url: str) -> None:
    import sqlalchemy as sa

    db = ConnectionResolver({"default": {"url": postgres_url}})
    PasswordResetToken.set_connection(db)
    RememberToken.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(PasswordResetToken.__table__))
        await db.execute(sa.schema.CreateTable(RememberToken.__table__))

        user = _User(1, "ada@example.com")

        async def lookup(email: str) -> _User | None:
            return user if email == user.email else None

        dispatcher = _RecordingDispatcher()
        broker = PasswordBroker(lookup, dispatcher=dispatcher)

        assert await broker.send_reset_link(user.email) is PasswordResetStatus.RESET_SUCCESS
        requested = dispatcher.events[0]
        token = requested.token

        # replaying a send within the throttle window is rejected
        assert await broker.send_reset_link(user.email) is PasswordResetStatus.RESET_THROTTLED

        status = await broker.reset(user.email, token, "correct-horse-battery", _set_password)
        assert status is PasswordResetStatus.RESET_SUCCESS
        assert user.password == "hash(correct-horse-battery)"

        # single-use: the row is gone, so replaying the SAME token now fails — the A6 fix
        replay = await broker.reset(user.email, token, "another-password", _set_password)
        assert replay is PasswordResetStatus.INVALID_TOKEN

        assert (await PasswordResetToken.where(email=user.email).first()) is None
    finally:
        await db.dispose()
