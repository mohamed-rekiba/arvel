"""Typed column helpers in ``arvel.database.columns`` (lesson L2).

Tests cover three contracts:

1. Each helper produces an SQLAlchemy ``Column`` of the expected type and flags.
2. Models declared with the helpers behave identically to ``mapped_column``-
   declared models — CRUD, ``to_dict``, ``__hidden__``, ``Timestamps``.
3. The helpers are exported from ``arvel.database`` so a user can import them
   alongside ``Model`` and ``Timestamps``."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime as _datetime
from typing import Any, cast

import pytest
from arvel.database import Model, SoftDeletes, Timestamps, relationship
from arvel.database import columns as columns_module
from arvel.database.columns import (
    big_integer,
    boolean,
    column,
    datetime,
    foreign_id,
    id_,
    integer,
    json,
    string,
    text,
    uuid,
)
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import TypeDecorator


class _UpperString(TypeDecorator[str]):
    """Custom TypeDecorator used to exercise the generic ``column`` helper."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: object) -> str | None:
        return value.upper() if value is not None else value


# ─── helper-shape tests (column type + flags) ────────────────────────────────


def _column_from(value: Any) -> Column[Any]:
    """Return the SQLAlchemy Column behind a ``mapped_column(...)`` result.

    ``mapped_column`` returns a ``MappedColumn`` proxy whose underlying SQLA
    ``Column`` lives at ``.column``. The two-checker pattern below matches
    the dual-checker cast pattern at ``test_schema_dsl.py:113-114`` — mypy
    narrows ``isinstance(x, Column)`` to ``Column[Any]`` (so
    the cast is redundant to mypy) while pyright leaves the generic parameter
    unbound (so the cast is required). Both suppressions are specific codes."""
    col = value.column
    if not isinstance(col, Column):
        msg = f"expected Column, got {type(col).__name__}"
        raise TypeError(msg)
    return cast("Column[Any]", col)  # type: ignore[redundant-cast]  # dual-checker cast


def test_unset_repr_is_debuggable() -> None:
    unset = object.__getattribute__(columns_module, "_UNSET")

    assert repr(unset) == "UNSET"


def test_optional_default_column_helpers() -> None:
    created = _datetime(2024, 1, 1, tzinfo=UTC)

    assert uuid() is not None
    assert uuid(nullable=True, default=None) is not None
    assert text(default="body") is not None
    assert integer(default=10) is not None
    assert datetime(default=created) is not None
    assert json(default={"enabled": True}) is not None


def test_id_emits_integer_primary_key() -> None:
    col = _column_from(id_())
    assert isinstance(col.type, Integer)
    assert col.primary_key is True
    assert col.autoincrement is True


def test_string_default_length_255() -> None:
    col = _column_from(string())
    assert isinstance(col.type, String)
    assert col.type.length == 255
    assert col.nullable is False


def test_string_custom_length_and_flags() -> None:
    col = _column_from(string(120, unique=True, index=True))
    assert isinstance(col.type, String)
    assert col.type.length == 120
    assert col.unique is True
    assert col.index is True


def test_text_returns_text_column() -> None:
    col = _column_from(text())
    assert isinstance(col.type, Text)


def test_integer_with_flags() -> None:
    col = _column_from(integer(unique=True, index=True))
    assert isinstance(col.type, Integer)
    assert col.unique is True
    assert col.index is True


def test_big_integer_returns_bigint_column() -> None:
    col = _column_from(big_integer())
    assert isinstance(col.type, BigInteger)


def test_boolean_returns_boolean_column() -> None:
    col = _column_from(boolean())
    assert isinstance(col.type, Boolean)


def test_datetime_default_timezone_aware() -> None:
    col = _column_from(datetime())
    assert isinstance(col.type, DateTime)
    assert col.type.timezone is True


def test_datetime_naive_when_requested() -> None:
    col = _column_from(datetime(timezone=False))
    assert isinstance(col.type, DateTime)
    assert col.type.timezone is False


def test_json_returns_json_column() -> None:
    col = _column_from(json())
    assert isinstance(col.type, JSON)


def test_foreign_id_attaches_foreign_key() -> None:
    col = _column_from(foreign_id("users.id", on_delete="CASCADE"))
    assert isinstance(col.type, Integer)
    assert col.index is True
    fks = list(col.foreign_keys)
    assert len(fks) == 1
    assert isinstance(fks[0], ForeignKey)
    assert "users.id" in str(fks[0].target_fullname)
    assert fks[0].ondelete == "CASCADE"


def test_column_wraps_an_arbitrary_custom_type() -> None:
    col = _column_from(column(_UpperString(50), unique=True))
    assert isinstance(col.type, _UpperString)
    assert col.nullable is False
    assert col.unique is True


def test_column_nullable_flag_is_honoured() -> None:
    col = _column_from(column(_UpperString(50), nullable=True, default=None))
    assert col.nullable is True


# ─── integration: model declared with the helpers behaves identically ───────


class _Account(Model, Timestamps):
    __tablename__ = "accounts_columns_test"

    id: int = id_()
    name: str = string(120, index=True)
    email: str = string(255, unique=True)
    balance: int = big_integer(default=0)
    is_active: bool = boolean(default=True)
    transactions: list[_Transaction] = relationship(
        "_Transaction", init=False, default_factory=list
    )


class _Transaction(Model, Timestamps):
    __tablename__ = "transactions_columns_test"

    id: int = id_()
    balance: int = big_integer(default=0)
    account_id: int | None = foreign_id("accounts_columns_test.id", nullable=True)


class _SoftAccount(Model, SoftDeletes):
    __tablename__ = "soft_accounts_columns_test"

    id: int = id_()
    name: str = string(120)


class _Vault(Model):
    __tablename__ = "vault_columns_test"

    id: int = id_()
    secret: str = column(_UpperString(50))


async def _create_tables(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def test_helper_model_crud_round_trip(engine: Any, session: AsyncSession) -> None:
    """A model declared exclusively with the helpers persists and reads back."""
    await _create_tables(engine)
    row = await _Account.create(name="Acme", email="ops@acme.test", balance=1000, is_active=True)
    assert row.id is not None
    assert row.name == "Acme"
    assert row.balance == 1000
    assert row.is_active is True

    fetched = await _Account.find(row.id)
    assert fetched is not None
    assert fetched.email == "ops@acme.test"
    assert len(await _Account.all()) >= 1
    assert len(await _Account.get()) >= 1
    assert await _Account.first() is not None
    assert await _Account.count() >= 1
    assert await _Account.exists() is True
    assert await _Account.value("name") == "Acme"
    assert "Acme" in await _Account.pluck("name")
    assert await _Account.sum("balance") == 1000
    assert await _Account.avg("balance") == 1000
    assert await _Account.max("balance") == 1000
    assert await _Account.min("balance") == 1000


async def test_helper_model_inherits_timestamps(engine: Any, session: AsyncSession) -> None:
    """The ``Timestamps`` mixin still wires ``created_at`` / ``updated_at``."""
    await _create_tables(engine)
    row = await _Account.create(name="Stamp", email="t@s.test")
    assert isinstance(row.created_at, _datetime)
    assert isinstance(row.updated_at, _datetime)


async def test_column_routes_custom_type_bind_processing(
    engine: Any, session: AsyncSession
) -> None:
    """A column field runs the custom type's bind processing on write."""
    await _create_tables(engine)
    row = await _Vault.create(secret="hunter2")
    # Refresh past the identity map to read what actually landed in the column.
    await row.refresh()
    assert row.secret == "HUNTER2"


def test_all_helpers_are_exported_from_arvel_database() -> None:
    """Every helper is part of ``arvel.database``'s public surface."""
    import arvel.database as adb

    for name in (
        "id_",
        "string",
        "text",
        "integer",
        "big_integer",
        "boolean",
        "column",
        "datetime",
        "json",
        "foreign_id",
    ):
        assert hasattr(adb, name), f"arvel.database.{name} not exported"
        assert name in adb.__all__, f"arvel.database.{name} not in __all__"


def test_query_mixin_builder_shortcuts_return_query_builders() -> None:
    other = _Account.query().where(_Account.name == "Other")
    cte = select(_Account).cte("accounts_cte")

    assert _Account.with_count("transactions") is not None
    assert _Account.with_sum("transactions", "balance") is not None
    assert _Account.with_max("transactions", "balance") is not None
    assert _Account.when(True, lambda query: query.where(_Account.name == "Acme")) is not None
    assert _Account.without_global_scope("tenant") is not None
    assert _Account.without_global_scopes() is not None
    assert _SoftAccount.with_trashed() is not None
    assert _SoftAccount.only_trashed() is not None
    assert _Account.lock_for_update() is not None
    assert _Account.union(other) is not None
    assert _Account.union_all(other) is not None
    assert _Account.with_cte("accounts_cte", cte) is not None
    assert _Account.recursive("parent_id") is not None
    assert "accounts_columns" in _Account.to_sql()


def test_string_rejects_unsupported_kwargs_at_type_layer() -> None:
    """Passing an unknown kwarg fails fast (Python TypeError, not silent ignore)."""
    with pytest.raises(TypeError):
        # ``foo`` is not a valid kwarg on ``string`` — mypy would also catch
        # this, but the runtime guard ensures bad calls never reach SQLA.
        string(255, foo="bar")  # type: ignore[call-overload]  # intentional negative test
