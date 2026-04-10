"""Database-aware validation rules.

Use parameterized SQLAlchemy expressions — never raw SQL or string interpolation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import column, select, table

from arvel.logging import Log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_log = Log.named("arvel.validation.rules.database")


class Unique:
    """Check that a value doesn't already exist in a database table.

    Optionally ignores a specific row (for update scenarios).
    """

    def __init__(
        self,
        table_name: str,
        column_name: str,
        *,
        session: AsyncSession | None,
        ignore: int | str | None = None,
        id_column: str = "id",
    ) -> None:
        self._table_name = table_name
        self._column_name = column_name
        self._session = session
        self._ignore = ignore
        self._id_column = id_column

    async def passes(self, attribute: str, value: Any, data: dict[str, Any]) -> bool:
        if self._session is None:
            msg = "Unique rule requires a database session"
            raise ValueError(msg)

        tbl = table(self._table_name, column(self._column_name), column(self._id_column))
        stmt = select(tbl.c[self._column_name]).where(tbl.c[self._column_name] == value)

        if self._ignore is not None:
            stmt = stmt.where(tbl.c[self._id_column] != self._ignore)

        try:
            result = await self._session.execute(stmt)
        except Exception:
            _log.exception(
                "Database error in Unique rule for %s.%s",
                self._table_name,
                self._column_name,
            )
            return False

        return result.first() is None

    def message(self) -> str:
        return f"The {self._column_name} has already been taken."


class Exists:
    """Check that a value exists in a database table."""

    def __init__(
        self,
        table_name: str,
        column_name: str,
        *,
        session: AsyncSession | None,
    ) -> None:
        self._table_name = table_name
        self._column_name = column_name
        self._session = session

    async def passes(self, attribute: str, value: Any, data: dict[str, Any]) -> bool:
        if self._session is None:
            msg = "Exists rule requires a database session"
            raise ValueError(msg)

        tbl = table(self._table_name, column(self._column_name))
        stmt = select(tbl.c[self._column_name]).where(tbl.c[self._column_name] == value)

        try:
            result = await self._session.execute(stmt)
        except Exception:
            _log.exception(
                "Database error in Exists rule for %s.%s",
                self._table_name,
                self._column_name,
            )
            return False

        return result.first() is not None

    def message(self) -> str:
        return f"The selected {self._column_name} is invalid."
