"""Console (doc 13) — ``auth:clear-resets`` deletes only expired password-reset tokens."""

from __future__ import annotations

import asyncio
from typing import Any

import sqlalchemy as sa
from typer.testing import CliRunner

from arvel.auth.password_reset import DEFAULT_TTL_SECONDS, PasswordBroker, PasswordResetToken
from arvel.console import build_cli
from arvel.database import ConnectionResolver
from arvel.dates import Date
from arvel.testing import travel_back, travel_to

runner = CliRunner()


class _User:
    def __init__(self, uid: int, email: str) -> None:
        self.id = uid
        self.email = email


def _lookup_for(users: dict[str, _User]) -> Any:
    async def _lookup(email: str) -> _User | None:
        return users.get(email)

    return _lookup


async def _seed() -> ConnectionResolver:
    db = ConnectionResolver()
    PasswordResetToken.set_connection(db)
    await db.execute(sa.schema.CreateTable(PasswordResetToken.__table__))

    users = {"expired@x.test": _User(1, "expired@x.test"), "live@x.test": _User(2, "live@x.test")}
    broker = PasswordBroker(_lookup_for(users))

    travel_to(Date.now().subtract(seconds=DEFAULT_TTL_SECONDS + 60))
    try:
        await broker.send_reset_link("expired@x.test")
    finally:
        travel_back()

    await broker.send_reset_link("live@x.test")
    return db


async def _remaining_emails() -> set[str]:
    rows = await PasswordResetToken.get()
    return {row.email for row in rows}


def test_auth_clear_resets_deletes_only_expired_rows() -> None:
    from arvel.kernel import Application, set_application

    asyncio.run(_seed())

    set_application(Application())
    try:
        result = runner.invoke(build_cli(), ["auth:clear-resets"])
    finally:
        set_application(None)

    assert result.exit_code == 0, result.output
    assert "deleted 1 expired password reset token" in result.output
    assert asyncio.run(_remaining_emails()) == {"live@x.test"}
