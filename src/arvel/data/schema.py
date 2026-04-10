"""Laravel-style Schema facade and Blueprint for migration authoring.

Provides a fluent, type-safe API for defining database tables in migrations
without importing Alembic or SQLAlchemy directly::

    from arvel.data import Schema, Blueprint

    def upgrade() -> None:
        def users(table: Blueprint) -> None:
            table.id()
            table.string("name")
            table.timestamps()

        Schema.create("users", users)
"""

from __future__ import annotations

import contextlib
import uuid
from enum import Enum, StrEnum
from typing import TYPE_CHECKING, Any, ClassVar, Self, cast

from alembic import op
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy import (
    inspect as sa_inspect,
)

if TYPE_CHECKING:
    from collections.abc import Callable


class KeyType(Enum):
    """Primary key column type."""

    INT = "int"
    BIG_INT = "bigint"
    UUID = "uuid"


class ForeignKeyAction(StrEnum):
    """Allowed ON DELETE / ON UPDATE actions."""

    CASCADE = "CASCADE"
    SET_NULL = "SET NULL"
    RESTRICT = "RESTRICT"
    NO_ACTION = "NO ACTION"
    SET_DEFAULT = "SET DEFAULT"


class ColumnBuilder:
    """Fluent builder for column constraints."""

    def __init__(self, column: Column[Any]) -> None:
        self._column = column

    def nullable(self) -> Self:
        self._column.nullable = True
        return self

    def unique(self) -> Self:
        self._column.unique = True
        return self

    def index(self) -> Self:
        self._column.index = True
        return self

    def default(self, value: object) -> Self:
        # SA Column.default is wider than stubs (scalars, callables, ColumnElement).
        cast("Any", self._column).default = value
        return self

    def server_default(self, value: str) -> Self:
        # SA server_default is wider than stubs (FetchedValue, TextClause, str, ...).
        cast("Any", self._column).server_default = value
        return self

    def _last_foreign_key(self) -> ForeignKey:
        foreign_keys = tuple(self._column.foreign_keys)
        if not foreign_keys:
            msg = "Cannot set on_delete/on_update before defining a foreign key reference"
            raise ValueError(msg)
        return foreign_keys[-1]

    def on_delete(self, action: ForeignKeyAction) -> Self:
        """Set ON DELETE behavior for the last attached foreign key."""
        foreign_key = self._last_foreign_key()
        cast("Any", foreign_key).ondelete = action.value
        return self

    def on_update(self, action: ForeignKeyAction) -> Self:
        """Set ON UPDATE behavior for the last attached foreign key."""
        foreign_key = self._last_foreign_key()
        cast("Any", foreign_key).onupdate = action.value
        return self

    def references(
        self,
        table: str,
        column: str = "id",
        *,
        on_delete: ForeignKeyAction | None = None,
        on_update: ForeignKeyAction | None = None,
    ) -> Self:
        """Attach an explicit foreign-key reference to this column.

        Generates a conventional constraint name ``fk_<col>_<table>`` so
        the FK works in both ``Schema.create()`` and ``Schema.table()``
        (Alembic batch mode requires named constraints).
        """
        target = f"{table}.{column}"
        fk_name = f"fk_{self._column.name}_{table}"
        self._column.append_foreign_key(ForeignKey(target, name=fk_name))
        if on_delete is not None:
            self.on_delete(on_delete)
        if on_update is not None:
            self.on_update(on_update)
        return self


class Blueprint:
    """Table definition builder — collects columns for a single table."""

    _KEY_TYPE_MAP: ClassVar[dict[KeyType, type]] = {
        KeyType.INT: Integer,
        KeyType.BIG_INT: BigInteger,
        KeyType.UUID: Uuid,
    }

    def __init__(self) -> None:
        self.columns: list[Column[Any]] = []

    def _add(self, col: Column[Any]) -> ColumnBuilder:
        self.columns.append(col)
        return ColumnBuilder(col)

    def id(self, name: str = "id", key_type: KeyType = KeyType.BIG_INT) -> ColumnBuilder:
        """Add an auto-incrementing or UUID primary key.

        For integer types, uses ``BigInteger`` with a ``Integer`` variant for
        SQLite — SQLite only auto-increments ``INTEGER PRIMARY KEY`` columns.
        """
        if key_type == KeyType.UUID:
            return self._add(Column(name, Uuid, primary_key=True, default=uuid.uuid7))
        sa_type = self._KEY_TYPE_MAP[key_type]
        col_type = sa_type().with_variant(Integer(), "sqlite")
        return self._add(Column(name, col_type, primary_key=True, autoincrement=True))

    def string(self, name: str, length: int = 255) -> ColumnBuilder:
        return self._add(Column(name, String(length), nullable=False))

    def text(self, name: str) -> ColumnBuilder:
        return self._add(Column(name, Text, nullable=False))

    def integer(self, name: str) -> ColumnBuilder:
        return self._add(Column(name, Integer, nullable=False))

    def big_integer(self, name: str) -> ColumnBuilder:
        return self._add(Column(name, BigInteger, nullable=False))

    def float_col(self, name: str) -> ColumnBuilder:
        return self._add(Column(name, Float, nullable=False))

    def decimal(self, name: str, precision: int = 8, scale: int = 2) -> ColumnBuilder:
        return self._add(Column(name, Numeric(precision=precision, scale=scale), nullable=False))

    def boolean(self, name: str) -> ColumnBuilder:
        return self._add(Column(name, Boolean, nullable=False, default=False))

    def uuid(self, name: str) -> ColumnBuilder:
        return self._add(Column(name, Uuid, nullable=False))

    def datetime(self, name: str) -> ColumnBuilder:
        return self._add(Column(name, DateTime(timezone=True), nullable=False))

    def timestamps(self) -> None:
        """Add created_at and updated_at columns."""
        self.columns.append(
            Column(
                "created_at",
                DateTime(timezone=True),
                nullable=False,
                server_default=func.now(),
            )
        )
        self.columns.append(
            Column(
                "updated_at",
                DateTime(timezone=True),
                nullable=False,
                server_default=func.now(),
                onupdate=func.now(),
            )
        )

    def soft_deletes(self) -> None:
        """Add a deleted_at column for soft deletes."""
        self.columns.append(Column("deleted_at", DateTime(timezone=True), nullable=True))

    def foreign_id(self, name: str) -> ColumnBuilder:
        """Add a BigInteger FK column (convention: <model>_id)."""
        return self._add(Column(name, BigInteger, nullable=False, index=True))


class Schema:
    """Static facade for table DDL operations."""

    @staticmethod
    def create(table_name: str, callback: Callable[[Blueprint], None]) -> None:
        """Create a new table from a Blueprint callback."""
        bp = Blueprint()
        callback(bp)
        op.create_table(table_name, *bp.columns)

    @staticmethod
    def table(table_name: str, callback: Callable[[Blueprint], None]) -> None:
        """Alter an existing table via a Blueprint callback.

        Indexes are created outside the batch context to avoid SQLite
        batch-mode issues where the copy-table process tries to recreate
        indexes on columns that may not exist in the target table.
        """
        bp = Blueprint()
        callback(bp)
        deferred_indexes: list[tuple[str, str]] = []
        with op.batch_alter_table(table_name) as batch:
            for col in bp.columns:
                if col.index:
                    col.index = False
                    idx_name = f"ix_{table_name}_{col.name}"
                    deferred_indexes.append((idx_name, col.name))
                batch.add_column(col)
        for idx_name, col_name in deferred_indexes:
            op.create_index(idx_name, table_name, [col_name])

    @staticmethod
    def drop_columns(table_name: str, *columns: str) -> None:
        """Remove columns (with their indexes and FK constraints) from a table.

        For each column this method:

        1. Drops the standalone index ``ix_{table}_{col}`` (created by
           :meth:`table`) **before** entering the batch — SQLite's
           copy-table process would otherwise try to recreate it on
           a column that no longer exists.
        2. Inside the batch, drops the FK constraint ``fk_{col}_*``
           (following the convention set by :meth:`ColumnBuilder.references`)
           and the column itself.
        """
        for col_name in columns:
            with contextlib.suppress(Exception):
                op.drop_index(f"ix_{table_name}_{col_name}", table_name=table_name)

        bind = op.get_context().connection
        if bind is None:
            msg = "drop_columns requires an active migration connection"
            raise RuntimeError(msg)
        insp = sa_inspect(bind)
        fk_names_to_drop: set[str] = set()
        col_set = set(columns)
        for fk in insp.get_foreign_keys(table_name):
            if fk.get("name") and col_set.intersection(fk.get("constrained_columns", ())):
                fk_names_to_drop.add(fk["name"])

        with op.batch_alter_table(table_name) as batch:
            for fk_name in fk_names_to_drop:
                batch.drop_constraint(fk_name, type_="foreignkey")
            for col_name in columns:
                batch.drop_column(col_name)

    @staticmethod
    def drop(table_name: str) -> None:
        """Drop a table."""
        op.drop_table(table_name)

    @staticmethod
    def rename(old_name: str, new_name: str) -> None:
        """Rename a table."""
        op.rename_table(old_name, new_name)
