"""ORM (doc 07) — HasUuids / HasUlids id strategies + Prunable. Test-first."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, HasUlids, HasUuids, Model, Prunable


class Token(HasUuids, Model):
    __fields__ = {"value": str}
    __fillable__ = ["value"]


class Ticket(HasUlids, Model):
    __fields__ = {"value": str}
    __fillable__ = ["value"]


class Stale(Prunable, Model):
    __fields__ = {"keep": bool}
    __fillable__ = ["keep"]

    @classmethod
    def prunable(cls) -> object:
        return cls.where(keep=False)


async def _table(model: type[Model], db: ConnectionResolver) -> None:
    model.set_connection(db)
    await db.execute(sa.schema.CreateTable(model.__table__))


async def test_has_uuids_generates_string_pk() -> None:
    db = ConnectionResolver()
    await _table(Token, db)
    try:
        token = await Token.create(value="secret")
        assert isinstance(token.id, str)
        assert len(token.id) >= 32  # a uuid string, not an int
        refetched = await Token.find(token.id)
        assert refetched is not None and refetched.value == "secret"
    finally:
        await db.dispose()


async def test_has_ulids_generates_26_char_pk() -> None:
    db = ConnectionResolver()
    await _table(Ticket, db)
    try:
        ticket = await Ticket.create(value="x")
        assert isinstance(ticket.id, str)
        assert len(ticket.id) == 26  # canonical ULID length
    finally:
        await db.dispose()


async def test_prunable_deletes_only_matching_rows() -> None:
    db = ConnectionResolver()
    await _table(Stale, db)
    try:
        await Stale.create(keep=True)
        await Stale.create(keep=False)
        await Stale.create(keep=False)

        await Stale.prune()
        remaining = await Stale.get()
        assert len(remaining) == 1  # only the keep=True row survives
    finally:
        await db.dispose()
