"""FR-003-015..019 — Scopes, accessors, mutators."""

from __future__ import annotations

from typing import Any, ClassVar

from arvel.database import GlobalScope, Model, QueryBuilder, accessor, id_, mutator, scope, string
from sqlalchemy.ext.asyncio import AsyncSession


class ActiveOnly(GlobalScope):
    def apply(self, qb: QueryBuilder[Any]) -> QueryBuilder[Any]:
        return qb.where_in("status", ["active"])


_global_scope = ActiveOnly()


class Account(Model):
    __tablename__ = "accounts_g"
    id: int = id_()
    first_name: str = string(50)
    last_name: str = string(50)
    status: str = string(20, default="active")

    __arvel_global_scopes__: ClassVar[dict[str, Any]] = {
        "active": _global_scope.apply,
    }

    @accessor
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @scope
    @staticmethod
    def named(qb: QueryBuilder[Account], name: str) -> QueryBuilder[Account]:
        return qb.where(first_name=name)


class Member(Model):
    __tablename__ = "members_mut"
    id: int = id_()
    name: str = string(50)
    password: str = string(200)

    @mutator("password")
    def set_password(self, value: str) -> str:
        return f"hashed:{value}"


async def _setup(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def test_global_scope_filters_by_default(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    await Account.create(first_name="A", last_name="X", status="active")
    await Account.create(first_name="B", last_name="Y", status="inactive")
    rows = await Account.all()
    assert len(rows) == 1
    assert rows[0].first_name == "A"


async def test_without_global_scope_returns_all_rows(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    await Account.create(first_name="A", last_name="X", status="active")
    await Account.create(first_name="B", last_name="Y", status="inactive")
    rows = await Account.without_global_scope("active").all()
    assert len(rows) == 2


async def test_local_scope_is_chainable(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    await Account.create(first_name="Ada", last_name="L", status="active")
    await Account.create(first_name="Bob", last_name="R", status="active")
    result = await Account.named("Ada").all()
    assert len(result) == 1
    assert result[0].first_name == "Ada"


async def test_accessor_is_readable(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    account = await Account.create(first_name="Ada", last_name="Lovelace")
    assert account.full_name == "Ada Lovelace"


def test_mutator_decorator_stores_metadata() -> None:
    class Sample:
        @mutator("password")
        def set_password(self, value: str) -> str:
            return value.upper()

    fn: Any = Sample.set_password
    assert fn.__arvel_mutator__ is True
    assert fn.__arvel_mutator_column__ == "password"


def test_mutator_transforms_value_on_construction() -> None:
    member = Member(name="Ada", password="secret")
    assert member.password == "hashed:secret"


def test_mutator_transforms_value_on_assignment() -> None:
    member = Member(name="Ada", password="secret")
    member.password = "rotated"
    assert member.password == "hashed:rotated"
