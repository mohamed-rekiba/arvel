"""BelongsToMany — many-to-many relation via an explicit pivot table."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass
from typing import Any, Generic, TypeVar, overload

from sqlalchemy import Table, delete, insert, select
from sqlalchemy import inspect as sa_inspect

from arvel.database.session import get_active_session

T = TypeVar("T")


@dataclass(frozen=True)
class BelongsToManyLink:
    """Pivot metadata for query-builder existence subqueries."""

    table: Table
    related_model: type[Any]
    foreign_key: str
    related_foreign_key: str


class BelongsToManyAccessor(Generic[T]):
    """Bound to an owner instance; exposes attach/detach/sync/pivot/toggle."""

    def __init__(
        self,
        owner: Any,
        related_model: type[T],
        table: Table,
        foreign_key: str,
        related_foreign_key: str,
    ) -> None:
        self._owner = owner
        self._related_model = related_model
        self._table = table
        self._fk = foreign_key
        self._rfk = related_foreign_key

    # ── async iteration ────────────────────────────────────────────────────

    def __aiter__(self) -> AsyncIterator[T]:
        return self._iter_related()

    async def _iter_related(self) -> AsyncGenerator[T]:
        session = get_active_session()
        mapper = sa_inspect(self._related_model)
        if mapper is None:
            raise TypeError(f"{self._related_model} is not a mapped SQLAlchemy class")
        pk_col = mapper.primary_key[0]
        stmt = (
            select(self._related_model)
            .join(self._table, self._table.c[self._rfk] == pk_col)
            .where(self._table.c[self._fk] == self._owner.id)
        )
        result = await session.execute(stmt)
        for row in result.scalars():
            yield row

    # ── pivot operations ────────────────────────────────────────────────────

    async def attach(self, related_id: int, **pivot_kwargs: Any) -> bool:
        """Insert pivot row. Returns True if new, False if already existed (upsert)."""
        session = get_active_session()
        check = (
            select(self._table)
            .where(self._table.c[self._fk] == self._owner.id)
            .where(self._table.c[self._rfk] == related_id)
        )
        existing = (await session.execute(check)).fetchone()
        if existing is not None:
            return False
        await session.execute(
            insert(self._table).values(
                **{self._fk: self._owner.id, self._rfk: related_id, **pivot_kwargs}
            )
        )
        await session.flush()
        return True

    async def detach(self, related_id: int) -> None:
        """Remove the pivot row for related_id. No-op if absent."""
        session = get_active_session()
        await session.execute(
            delete(self._table)
            .where(self._table.c[self._fk] == self._owner.id)
            .where(self._table.c[self._rfk] == related_id)
        )
        await session.flush()

    async def sync(self, related_ids: list[int]) -> None:
        """Replace all pivot rows with exactly related_ids."""
        session = get_active_session()
        stmt = select(self._table.c[self._rfk]).where(self._table.c[self._fk] == self._owner.id)
        current_ids: set[int] = set((await session.execute(stmt)).scalars())
        new_ids = set(related_ids)
        for rid in current_ids - new_ids:
            await self.detach(rid)
        for rid in new_ids - current_ids:
            await self.attach(rid)

    async def sync_without_detaching(self, related_ids: list[int]) -> None:
        """Attach related_ids that aren't already attached; never remove existing rows."""
        session = get_active_session()
        stmt = select(self._table.c[self._rfk]).where(self._table.c[self._fk] == self._owner.id)
        current_ids: set[int] = set((await session.execute(stmt)).scalars())
        for rid in set(related_ids) - current_ids:
            await self.attach(rid)

    async def where_pivot(self, column: str, value: Any) -> list[T]:
        """Filter the pivot table by a column value and return related records."""
        session = get_active_session()
        mapper = sa_inspect(self._related_model)
        if mapper is None:
            raise TypeError(f"{self._related_model} is not a mapped SQLAlchemy class")
        pk_col = mapper.primary_key[0]
        stmt = (
            select(self._related_model)
            .join(self._table, self._table.c[self._rfk] == pk_col)
            .where(self._table.c[self._fk] == self._owner.id)
            .where(self._table.c[column] == value)
        )
        result = await session.execute(stmt)
        return list(result.scalars())

    async def pivot(self, related_id: int) -> dict[str, Any] | None:
        """Return the pivot row as a dict, or None if the row doesn't exist."""
        session = get_active_session()
        check = (
            select(self._table)
            .where(self._table.c[self._fk] == self._owner.id)
            .where(self._table.c[self._rfk] == related_id)
        )
        row = (await session.execute(check)).mappings().fetchone()
        if row is None:
            return None
        return dict(row)

    async def toggle(self, related_id: int) -> str:
        """Attach if absent, detach if present. Returns 'attached' or 'detached'."""
        session = get_active_session()
        check = (
            select(self._table)
            .where(self._table.c[self._fk] == self._owner.id)
            .where(self._table.c[self._rfk] == related_id)
        )
        existing = (await session.execute(check)).fetchone()
        if existing is None:
            await self.attach(related_id)
            return "attached"
        await self.detach(related_id)
        return "detached"


class BelongsToMany(Generic[T]):
    """Descriptor for many-to-many relations via a pivot table.

    Usage::

        class Post(Model):
            tags: BelongsToMany[Tag] = BelongsToMany(
                Tag, table=post_tag_table, foreign_key="post_id", related_foreign_key="tag_id"
            )
    """

    def __init__(
        self,
        related_model: type[T],
        *,
        table: Table,
        foreign_key: str,
        related_foreign_key: str,
    ) -> None:
        self._related_model = related_model
        self._table = table
        self._fk = foreign_key
        self._rfk = related_foreign_key

    @property
    def table(self) -> Table:
        return self._table

    @property
    def related_model(self) -> type[T]:
        return self._related_model

    @property
    def foreign_key(self) -> str:
        return self._fk

    @property
    def related_foreign_key(self) -> str:
        return self._rfk

    def link_spec(self) -> BelongsToManyLink:
        return BelongsToManyLink(
            table=self._table,
            related_model=self._related_model,
            foreign_key=self._fk,
            related_foreign_key=self._rfk,
        )

    @overload
    def __get__(self, obj: None, objtype: type) -> BelongsToMany[T]: ...

    @overload
    def __get__(self, obj: Any, objtype: type) -> BelongsToManyAccessor[T]: ...

    def __get__(
        self, obj: Any, objtype: type | None = None
    ) -> BelongsToMany[T] | BelongsToManyAccessor[T]:
        if obj is None:
            return self
        return BelongsToManyAccessor(
            owner=obj,
            related_model=self._related_model,
            table=self._table,
            foreign_key=self._fk,
            related_foreign_key=self._rfk,
        )

    # Class-level method declarations so that feature-existence checks like
    # ``hasattr(BelongsToMany, "sync_without_detaching")`` succeed without
    # aliasing the generic ``BelongsToManyAccessor`` methods (which would
    # propagate ``BelongsToManyAccessor[Unknown]`` to every reader). Real
    # behaviour lives on the accessor returned from ``__get__``; calling
    # these directly on the descriptor (not through an instance) is a
    # programming error and is reported as such.

    async def sync_without_detaching(self, related_ids: list[int]) -> None:
        raise TypeError(
            "BelongsToMany.sync_without_detaching must be called on an instance "
            "(e.g. post.tags.sync_without_detaching([...])), not on the descriptor."
        )

    async def where_pivot(self, column: str, value: Any) -> list[T]:
        raise TypeError(
            "BelongsToMany.where_pivot must be called on an instance "
            "(e.g. post.tags.where_pivot(...)), not on the descriptor."
        )
