"""Pivot table manager for belongs_to_many relationships.

Provides attach, detach, and sync operations on the association table,
all using parameterized queries within the owning session's transaction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, insert, select

if TYPE_CHECKING:
    from sqlalchemy import Column, Table
    from sqlalchemy.ext.asyncio import AsyncSession


class PivotManager:
    """Manages rows in a many-to-many pivot table for one side of the relationship.

    All mutations happen through the session and are flushed immediately so
    callers can read back consistent state within the same transaction.
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        pivot_table: Table,
        owner_fk_column: Column[Any],
        related_fk_column: Column[Any],
        owner_id: int | str,
    ) -> None:
        self._session = session
        self._pivot = pivot_table
        self._owner_col = owner_fk_column
        self._related_col = related_fk_column
        self._owner_id = owner_id

    async def attach(self, related_id: int | str, **extra: str | int | float | bool | None) -> None:
        """Insert a pivot row linking owner to related_id.

        Extra kwargs are written to additional pivot columns if they exist.
        """
        values: dict[str, str | int | float | bool | None] = {
            self._owner_col.name: self._owner_id,
            self._related_col.name: related_id,
            **extra,
        }
        stmt = insert(self._pivot).values(values)
        await self._session.execute(stmt)
        await self._session.flush()

    async def detach(self, related_id: int | str) -> None:
        """Remove the pivot row linking owner to related_id."""
        stmt = (
            delete(self._pivot)
            .where(self._owner_col == self._owner_id)
            .where(self._related_col == related_id)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def sync(self, related_ids: list[int | str]) -> None:
        """Replace all pivot rows for owner with exactly the given related_ids.

        Operates atomically: removes extras, batch-inserts missing.
        """
        current_stmt = select(self._related_col).where(self._owner_col == self._owner_id)
        result = await self._session.execute(current_stmt)
        current_ids: set[int | str] = {row[0] for row in result.all()}
        desired: set[int | str] = set(related_ids)

        to_remove = current_ids - desired
        to_add = desired - current_ids

        if to_remove:
            stmt = (
                delete(self._pivot)
                .where(self._owner_col == self._owner_id)
                .where(self._related_col.in_(to_remove))
            )
            await self._session.execute(stmt)

        if to_add:
            rows = [
                {self._owner_col.name: self._owner_id, self._related_col.name: rid}
                for rid in to_add
            ]
            await self._session.execute(insert(self._pivot), rows)

        await self._session.flush()

    async def ids(self) -> list[int | str]:
        """Return all related IDs currently linked via the pivot table."""
        stmt = select(self._related_col).where(self._owner_col == self._owner_id)
        result = await self._session.execute(stmt)
        return [row[0] for row in result.all()]
