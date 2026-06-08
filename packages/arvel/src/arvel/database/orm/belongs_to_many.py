"""BelongsToMany — many-to-many relation via an explicit pivot table."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Generic, TypedDict, TypeVar, cast, overload

from sqlalchemy import Table, delete, insert, select, update
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Mapper

from arvel.database.orm._eager import clear_eager_relation, get_eager_relation
from arvel.database.session import get_active_session

if TYPE_CHECKING:
    from arvel.database.model import Model

T = TypeVar("T")

# Either a plain list of related IDs, or {id: {pivot_col: value, ...}}.
SyncIds = list[int] | Mapping[int, Mapping[str, Any]]


class SyncResult(TypedDict):
    """What sync() changed, mirroring Eloquent's return shape."""

    attached: list[int]
    detached: list[int]
    updated: list[int]


def normalize_sync_ids(ids: SyncIds) -> dict[int, dict[str, Any]]:
    """Coerce list or mapping form into {id: pivot_attrs}. Shared with MorphToMany."""
    if isinstance(ids, Mapping):
        return {int(k): dict(v) for k, v in ids.items()}
    return {int(i): {} for i in ids}


@dataclass(frozen=True)
class BelongsToManyLink:
    """Pivot metadata for query-builder existence subqueries."""

    table: Table
    related_model: type[Any]
    foreign_key: str
    related_foreign_key: str


@dataclass(frozen=True)
class PivotConfig:
    """Per-relation pivot ergonomics: extra columns, timestamps, accessor name."""

    columns: tuple[str, ...] = ()
    timestamps: bool = False
    created_at: str = "created_at"
    updated_at: str = "updated_at"
    accessor: str = "pivot"

    def select_columns(self) -> list[str]:
        cols = list(self.columns)
        if self.timestamps:
            for ts in (self.created_at, self.updated_at):
                if ts not in cols:
                    cols.append(ts)
        return cols


class BelongsToManyAccessor(Generic[T]):
    """Bound to an owner instance; exposes attach/detach/sync/pivot/toggle."""

    def __init__(
        self,
        owner: Model,
        related_model: type[T],
        table: Table,
        foreign_key: str,
        related_foreign_key: str,
        attr_name: str | None = None,
        pivot: PivotConfig | None = None,
    ) -> None:
        self._owner = owner
        self._related_model = related_model
        self._table = table
        self._fk = foreign_key
        self._rfk = related_foreign_key
        self._attr_name = attr_name
        self._pivot = pivot or PivotConfig()
        # Resolve the owner PK column name once; reads stay lazy so a freshly
        # flushed autoincrement id is picked up. Supports non-"id" / UUID PKs.
        owner_mapper: Mapper[Any] = cast("Mapper[Any]", sa_inspect(type(owner)))
        pk_key = owner_mapper.primary_key[0].key
        if pk_key is None:
            raise TypeError(f"{type(owner).__name__} primary key column has no key")
        self._owner_key: str = pk_key

    def _related_pk_col(self) -> Any:
        mapper = sa_inspect(self._related_model)
        if mapper is None:
            raise TypeError(f"{self._related_model} is not a mapped SQLAlchemy class")
        return mapper.primary_key[0]

    def _global_scope_clause(self) -> Any:
        """Related model's global-scope predicate (soft-delete `deleted_at IS NULL`), or None."""
        # Deferred import: query.py imports the orm package, so this can't be top-level.
        from arvel.database.query import QueryBuilder

        related: type[Any] = self._related_model
        return QueryBuilder(related, select(related)).apply_global_scopes().whereclause

    def _hydrate_pivot(self, rows: Sequence[Any], pivot_cols: Sequence[str]) -> list[T]:
        """Attach a pivot namespace (the configured accessor name) onto each related row."""
        items: list[T] = []
        for row in rows:
            obj = row[0]
            data = {col: row[i + 1] for i, col in enumerate(pivot_cols)}
            object.__setattr__(obj, self._pivot.accessor, SimpleNamespace(**data))
            items.append(cast("T", obj))
        return items

    async def _fetch(
        self, *predicates: Any, order_col: str | None = None, order_desc: bool = False
    ) -> list[T]:
        """Run the join query with optional pivot filters/order, hydrating pivot data."""
        session = get_active_session()
        pk_col = self._related_pk_col()
        pivot_cols = self._pivot.select_columns()
        extra = [self._table.c[c] for c in pivot_cols]
        stmt = (
            select(self._related_model, *extra)
            .join(self._table, self._table.c[self._rfk] == pk_col)
            .where(self._table.c[self._fk] == self._owner_id)
        )
        scope_where = self._global_scope_clause()
        if scope_where is not None:
            stmt = stmt.where(scope_where)
        for pred in predicates:
            stmt = stmt.where(pred)
        if order_col is not None:
            col = self._table.c[order_col]
            stmt = stmt.order_by(col.desc() if order_desc else col.asc())
        result = await session.execute(stmt)
        if not pivot_cols:
            return list(result.scalars())
        return self._hydrate_pivot(result.all(), pivot_cols)

    def _invalidate_cache(self) -> None:
        if self._attr_name is not None:
            clear_eager_relation(self._owner, self._attr_name)

    @property
    def _owner_id(self) -> Any:
        return getattr(self._owner, self._owner_key)

    # ── async iteration ────────────────────────────────────────────────────

    def __aiter__(self) -> AsyncIterator[T]:
        return self._iter_related()

    async def _iter_related(self) -> AsyncGenerator[T]:
        if self._attr_name is not None:
            cached = get_eager_relation(self._owner, self._attr_name)
            if cached is not None:
                for row in cached:
                    yield cast("T", row)
                return
        for row in await self._fetch():
            yield row

    async def all(self) -> list[T]:
        """Return all related rows attached to this owner (with pivot data if configured)."""
        if self._attr_name is not None:
            cached = get_eager_relation(self._owner, self._attr_name)
            if cached is not None:
                return [cast("T", row) for row in cached]
        return await self._fetch()

    # ── pivot queries ─────────────────────────────────────────────────────────

    async def order_by_pivot(self, column: str, direction: str = "asc") -> list[T]:
        """Related rows ordered by a pivot column."""
        return await self._fetch(order_col=column, order_desc=direction.lower() == "desc")

    async def where_pivot_in(self, column: str, values: Sequence[Any]) -> list[T]:
        """Related rows whose pivot column is in ``values``."""
        return await self._fetch(self._table.c[column].in_(list(values)))

    async def where_pivot_not_in(self, column: str, values: Sequence[Any]) -> list[T]:
        """Related rows whose pivot column is not in ``values``."""
        return await self._fetch(self._table.c[column].notin_(list(values)))

    async def where_pivot_between(self, column: str, low: Any, high: Any) -> list[T]:
        """Related rows whose pivot column is between ``low`` and ``high`` (inclusive)."""
        return await self._fetch(self._table.c[column].between(low, high))

    async def where_pivot_null(self, column: str, *, negate: bool = False) -> list[T]:
        """Related rows whose pivot column is NULL (or NOT NULL when ``negate``)."""
        col = self._table.c[column]
        return await self._fetch(col.isnot(None) if negate else col.is_(None))

    # ── pivot operations ────────────────────────────────────────────────────

    def _with_timestamps(self, values: dict[str, Any], *, creating: bool) -> dict[str, Any]:
        """Fill pivot created_at/updated_at when timestamps are enabled and unset."""
        if not self._pivot.timestamps:
            return values
        now = datetime.now(UTC)
        if creating:
            values.setdefault(self._pivot.created_at, now)
        values.setdefault(self._pivot.updated_at, now)
        return values

    async def attach(self, related_id: int, **pivot_kwargs: Any) -> bool:
        """Insert pivot row. Returns True if new, False if already existed (upsert)."""
        session = get_active_session()
        check = (
            select(self._table)
            .where(self._table.c[self._fk] == self._owner_id)
            .where(self._table.c[self._rfk] == related_id)
        )
        existing = (await session.execute(check)).fetchone()
        if existing is not None:
            return False
        values = self._with_timestamps(
            {self._fk: self._owner_id, self._rfk: related_id, **pivot_kwargs}, creating=True
        )
        await session.execute(insert(self._table).values(**values))
        await session.flush()
        self._invalidate_cache()
        return True

    async def detach(self, related_id: int) -> None:
        """Remove the pivot row for related_id. No-op if absent."""
        session = get_active_session()
        await session.execute(
            delete(self._table)
            .where(self._table.c[self._fk] == self._owner_id)
            .where(self._table.c[self._rfk] == related_id)
        )
        await session.flush()
        self._invalidate_cache()

    async def update_pivot(self, related_id: int, attrs: Mapping[str, Any]) -> bool:
        """Update pivot columns on an existing row. Returns True if a row changed."""
        if not attrs:
            return False
        session = get_active_session()
        values = self._with_timestamps(dict(attrs), creating=False)
        result = cast(
            "CursorResult[Any]",
            await session.execute(
                update(self._table)
                .where(self._table.c[self._fk] == self._owner_id)
                .where(self._table.c[self._rfk] == related_id)
                .values(**values)
            ),
        )
        await session.flush()
        return int(result.rowcount) > 0

    async def create(self, pivot: Mapping[str, Any] | None = None, **attributes: Any) -> T:
        """Create a related model and attach it to this owner. Returns the new model."""
        related = await cast("Any", self._related_model).create(**attributes)
        await self.attach(related.get_key(), **dict(pivot or {}))
        return cast("T", related)

    async def save(self, instance: T, pivot: Mapping[str, Any] | None = None) -> T:
        """Persist ``instance`` if needed, then attach it to this owner."""
        model = cast("Any", instance)
        pk_col = self._related_pk_col()
        if getattr(model, pk_col.key, None) is None:
            await model.save()
        await self.attach(model.get_key(), **dict(pivot or {}))
        return instance

    async def sync(self, related_ids: SyncIds) -> SyncResult:
        """Replace pivot rows so they match related_ids, returning what changed.

        Accepts a list of IDs or ``{id: {pivot_col: value}}`` to set pivot data.
        """
        session = get_active_session()
        desired = normalize_sync_ids(related_ids)
        stmt = select(self._table.c[self._rfk]).where(self._table.c[self._fk] == self._owner_id)
        current_ids: set[int] = set((await session.execute(stmt)).scalars())
        result: SyncResult = {"attached": [], "detached": [], "updated": []}
        for rid in current_ids - set(desired):
            await self.detach(rid)
            result["detached"].append(rid)
        for rid, attrs in desired.items():
            if rid not in current_ids:
                await self.attach(rid, **attrs)
                result["attached"].append(rid)
            elif await self.update_pivot(rid, attrs):
                result["updated"].append(rid)
        return result

    async def sync_without_detaching(self, related_ids: SyncIds) -> SyncResult:
        """Attach/update related_ids without removing existing rows; report changes."""
        session = get_active_session()
        desired = normalize_sync_ids(related_ids)
        stmt = select(self._table.c[self._rfk]).where(self._table.c[self._fk] == self._owner_id)
        current_ids: set[int] = set((await session.execute(stmt)).scalars())
        result: SyncResult = {"attached": [], "detached": [], "updated": []}
        for rid, attrs in desired.items():
            if rid not in current_ids:
                await self.attach(rid, **attrs)
                result["attached"].append(rid)
            elif await self.update_pivot(rid, attrs):
                result["updated"].append(rid)
        return result

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
            .where(self._table.c[self._fk] == self._owner_id)
            .where(self._table.c[column] == value)
        )
        result = await session.execute(stmt)
        return list(result.scalars())

    async def pivot(self, related_id: int) -> dict[str, Any] | None:
        """Return the pivot row as a dict, or None if the row doesn't exist."""
        session = get_active_session()
        check = (
            select(self._table)
            .where(self._table.c[self._fk] == self._owner_id)
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
            .where(self._table.c[self._fk] == self._owner_id)
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
        self._attr_name: str | None = None
        self._pivot = PivotConfig()

    def __set_name__(self, owner: type[Any], name: str) -> None:
        self._attr_name = name

    # ── fluent pivot configuration (Eloquent-style, applied at class definition) ──

    def with_pivot(self, *columns: str) -> BelongsToMany[T]:
        """Hydrate extra pivot columns onto each related row's pivot accessor."""
        self._pivot = replace(self._pivot, columns=(*self._pivot.columns, *columns))
        return self

    def with_timestamps(
        self, created_at: str = "created_at", updated_at: str = "updated_at"
    ) -> BelongsToMany[T]:
        """Maintain pivot ``created_at``/``updated_at`` on attach/sync/update."""
        self._pivot = replace(
            self._pivot, timestamps=True, created_at=created_at, updated_at=updated_at
        )
        return self

    def as_(self, accessor: str) -> BelongsToMany[T]:
        """Name the pivot accessor attached to related rows (Eloquent's ``as``)."""
        self._pivot = replace(self._pivot, accessor=accessor)
        return self

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
            attr_name=self._attr_name,
            pivot=self._pivot,
        )

    # Class-level method declarations so that feature-existence checks like
    # ``hasattr(BelongsToMany, "sync_without_detaching")`` succeed without
    # aliasing the generic ``BelongsToManyAccessor`` methods (which would
    # propagate ``BelongsToManyAccessor[Unknown]`` to every reader). Real
    # behaviour lives on the accessor returned from ``__get__``; calling
    # these directly on the descriptor (not through an instance) is a
    # programming error and is reported as such.

    async def sync_without_detaching(self, related_ids: SyncIds) -> SyncResult:
        raise TypeError(
            "BelongsToMany.sync_without_detaching must be called on an instance "
            "(e.g. post.tags.sync_without_detaching([...])), not on the descriptor."
        )

    async def where_pivot(self, column: str, value: Any) -> list[T]:
        raise TypeError(
            "BelongsToMany.where_pivot must be called on an instance "
            "(e.g. post.tags.where_pivot(...)), not on the descriptor."
        )
