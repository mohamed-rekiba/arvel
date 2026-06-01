"""MorphToMany — polymorphic many-to-many via a pivot table with a type discriminator.

Like :class:`BelongsToMany`, but the pivot carries ``{name}_type`` / ``{name}_id``
columns instead of a single
owner foreign key. One pivot table can therefore link many owner types to the
same related model — e.g. ``model_has_roles`` linking both ``User`` and ``Team``
to ``Role``.

The owner id is always written and compared as a string so a VARCHAR pivot
column accepts integer, UUID, and string primary keys without a dialect-specific
cast on INSERT.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast, overload

from sqlalchemy import String, Table, delete, insert, select, update
from sqlalchemy import cast as sa_cast
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Mapper

from arvel.database.orm._eager import clear_eager_relation, get_eager_relation
from arvel.database.orm.belongs_to_many import SyncIds, SyncResult, normalize_sync_ids
from arvel.database.orm.morph_map import get_morph_alias
from arvel.database.session import get_active_session

if TYPE_CHECKING:
    from arvel.database.model import Model

T = TypeVar("T")


@dataclass(frozen=True)
class MorphToManyLink:
    """Pivot metadata for query-builder existence subqueries.

    ``owner_type`` is filled in by the query builder from the owning model's
    class name; the descriptor itself doesn't know which class it lives on.
    """

    table: Table
    related_model: type[Any]
    type_column: str
    id_column: str
    related_foreign_key: str
    owner_type: str


class MorphToManyAccessor(Generic[T]):
    """Bound to an owner instance; exposes attach/detach/sync/pivot/toggle/all."""

    def __init__(
        self,
        owner: Model,
        related_model: type[T],
        table: Table,
        type_column: str,
        id_column: str,
        related_foreign_key: str,
        attr_name: str | None = None,
    ) -> None:
        self._owner = owner
        self._related_model = related_model
        self._table = table
        self._type_col = type_column
        self._id_col = id_column
        self._rfk = related_foreign_key
        self._attr_name = attr_name
        owner_mapper: Mapper[Any] = cast("Mapper[Any]", sa_inspect(type(owner)))
        pk_key = owner_mapper.primary_key[0].key
        if pk_key is None:
            raise TypeError(f"{type(owner).__name__} primary key column has no key")
        self._owner_key: str = pk_key

    def _invalidate_cache(self) -> None:
        if self._attr_name is not None:
            clear_eager_relation(self._owner, self._attr_name)

    @property
    def _owner_type(self) -> str:
        return get_morph_alias(type(self._owner))

    @property
    def _owner_id(self) -> str:
        # VARCHAR pivot column — coerce here so int/UUID PKs round-trip cleanly.
        return str(getattr(self._owner, self._owner_key))

    def _owner_where(self) -> tuple[Any, Any]:
        return (
            self._table.c[self._type_col] == self._owner_type,
            self._table.c[self._id_col] == self._owner_id,
        )

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
        session = get_active_session()
        mapper = sa_inspect(self._related_model)
        if mapper is None:
            raise TypeError(f"{self._related_model} is not a mapped SQLAlchemy class")
        pk_col = mapper.primary_key[0]
        type_pred, id_pred = self._owner_where()
        stmt = (
            select(self._related_model)
            .join(self._table, self._table.c[self._rfk] == pk_col)
            .where(type_pred)
            .where(id_pred)
        )
        result = await session.execute(stmt)
        for row in result.scalars():
            yield row

    async def all(self) -> list[T]:
        """Return all related rows attached to this owner."""
        return [row async for row in self]

    # ── pivot operations ────────────────────────────────────────────────────

    async def attach(self, related_id: int, **pivot_kwargs: Any) -> bool:
        """Insert pivot row. Returns True if new, False if already existed (upsert)."""
        session = get_active_session()
        type_pred, id_pred = self._owner_where()
        check = (
            select(self._table)
            .where(type_pred)
            .where(id_pred)
            .where(self._table.c[self._rfk] == related_id)
        )
        existing = (await session.execute(check)).fetchone()
        if existing is not None:
            return False
        await session.execute(
            insert(self._table).values(
                **{
                    self._type_col: self._owner_type,
                    self._id_col: self._owner_id,
                    self._rfk: related_id,
                    **pivot_kwargs,
                }
            )
        )
        await session.flush()
        self._invalidate_cache()
        return True

    async def detach(self, related_id: int) -> None:
        """Remove the pivot row for related_id. No-op if absent."""
        session = get_active_session()
        type_pred, id_pred = self._owner_where()
        await session.execute(
            delete(self._table)
            .where(type_pred)
            .where(id_pred)
            .where(self._table.c[self._rfk] == related_id)
        )
        await session.flush()
        self._invalidate_cache()

    async def update_pivot(self, related_id: int, attrs: Mapping[str, Any]) -> bool:
        """Update pivot columns on an existing row. Returns True if a row changed."""
        if not attrs:
            return False
        session = get_active_session()
        type_pred, id_pred = self._owner_where()
        result = cast(
            "CursorResult[Any]",
            await session.execute(
                update(self._table)
                .where(type_pred)
                .where(id_pred)
                .where(self._table.c[self._rfk] == related_id)
                .values(**dict(attrs))
            ),
        )
        await session.flush()
        return int(result.rowcount) > 0

    async def _current_ids(self) -> set[int]:
        session = get_active_session()
        type_pred, id_pred = self._owner_where()
        stmt = select(self._table.c[self._rfk]).where(type_pred).where(id_pred)
        return set((await session.execute(stmt)).scalars())

    async def sync(self, related_ids: SyncIds) -> SyncResult:
        """Replace pivot rows so they match related_ids, returning what changed."""
        desired = normalize_sync_ids(related_ids)
        current_ids = await self._current_ids()
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
        desired = normalize_sync_ids(related_ids)
        current_ids = await self._current_ids()
        result: SyncResult = {"attached": [], "detached": [], "updated": []}
        for rid, attrs in desired.items():
            if rid not in current_ids:
                await self.attach(rid, **attrs)
                result["attached"].append(rid)
            elif await self.update_pivot(rid, attrs):
                result["updated"].append(rid)
        return result

    async def toggle(self, related_id: int) -> str:
        """Attach if absent, detach if present. Returns 'attached' or 'detached'."""
        if related_id in await self._current_ids():
            await self.detach(related_id)
            return "detached"
        await self.attach(related_id)
        return "attached"

    async def where_pivot(self, column: str, value: Any) -> list[T]:
        """Filter the pivot table by a column value and return related records."""
        session = get_active_session()
        mapper = sa_inspect(self._related_model)
        if mapper is None:
            raise TypeError(f"{self._related_model} is not a mapped SQLAlchemy class")
        pk_col = mapper.primary_key[0]
        type_pred, id_pred = self._owner_where()
        stmt = (
            select(self._related_model)
            .join(self._table, self._table.c[self._rfk] == pk_col)
            .where(type_pred)
            .where(id_pred)
            .where(self._table.c[column] == value)
        )
        result = await session.execute(stmt)
        return list(result.scalars())

    async def pivot(self, related_id: int) -> dict[str, Any] | None:
        """Return the pivot row as a dict, or None if the row doesn't exist."""
        session = get_active_session()
        type_pred, id_pred = self._owner_where()
        check = (
            select(self._table)
            .where(type_pred)
            .where(id_pred)
            .where(self._table.c[self._rfk] == related_id)
        )
        row = (await session.execute(check)).mappings().fetchone()
        if row is None:
            return None
        return dict(row)


class MorphToMany(Generic[T]):
    """Descriptor for a polymorphic many-to-many relation via a pivot table.

    Usage::

        class User(Model):
            roles: ClassVar[MorphToMany[Role]] = MorphToMany(
                Role, table=model_has_roles, name="model", related_key="role_id"
            )
    """

    def __init__(
        self,
        related_model: type[T],
        *,
        table: Table,
        name: str,
        related_key: str,
    ) -> None:
        self._related_model = related_model
        self._table = table
        self._name = name
        self._type_col = f"{name}_type"
        self._id_col = f"{name}_id"
        self._rfk = related_key
        self._attr_name: str | None = None

    def __set_name__(self, owner: type[Any], name: str) -> None:
        self._attr_name = name

    @property
    def table(self) -> Table:
        return self._table

    @property
    def related_model(self) -> type[T]:
        return self._related_model

    @property
    def type_column(self) -> str:
        return self._type_col

    @property
    def id_column(self) -> str:
        return self._id_col

    @property
    def related_foreign_key(self) -> str:
        return self._rfk

    def link_spec(self, owner_type: str) -> MorphToManyLink:
        return MorphToManyLink(
            table=self._table,
            related_model=self._related_model,
            type_column=self._type_col,
            id_column=self._id_col,
            related_foreign_key=self._rfk,
            owner_type=owner_type,
        )

    @overload
    def __get__(self, obj: None, objtype: type) -> MorphToMany[T]: ...

    @overload
    def __get__(self, obj: Any, objtype: type) -> MorphToManyAccessor[T]: ...

    def __get__(
        self, obj: Any, objtype: type | None = None
    ) -> MorphToMany[T] | MorphToManyAccessor[T]:
        if obj is None:
            return self
        return MorphToManyAccessor(
            owner=obj,
            related_model=self._related_model,
            table=self._table,
            type_column=self._type_col,
            id_column=self._id_col,
            related_foreign_key=self._rfk,
            attr_name=self._attr_name,
        )


@dataclass(frozen=True)
class MorphedByManyLink:
    """Pivot metadata for the inverse of MorphToMany (the polymorphic side).

    ``related_type`` pins the morph discriminator to the *related* model's alias,
    and ``owner_foreign_key`` is the pivot column holding the owner's own PK.
    """

    table: Table
    related_model: type[Any]
    type_column: str
    id_column: str
    owner_foreign_key: str
    related_type: str


class MorphedByManyAccessor(Generic[T]):
    """Inverse of MorphToMany: e.g. ``tag.posts`` over the ``taggables`` pivot.

    The pivot's ``{name}_type``/``{name}_id`` describe the *related* rows, and a
    plain owner FK column (``related_key``) holds this owner's PK. So we filter
    ``{name}_type == alias(related)`` and join ``{name}_id`` back to the related
    PK (string-cast, since the column is VARCHAR).
    """

    def __init__(
        self,
        owner: Model,
        related_model: type[T],
        table: Table,
        type_column: str,
        id_column: str,
        owner_foreign_key: str,
        attr_name: str | None = None,
    ) -> None:
        self._owner = owner
        self._related_model = related_model
        self._table = table
        self._type_col = type_column
        self._id_col = id_column
        self._ofk = owner_foreign_key
        self._attr_name = attr_name
        owner_mapper: Mapper[Any] = cast("Mapper[Any]", sa_inspect(type(owner)))
        pk_key = owner_mapper.primary_key[0].key
        if pk_key is None:
            raise TypeError(f"{type(owner).__name__} primary key column has no key")
        self._owner_key: str = pk_key

    def _invalidate_cache(self) -> None:
        if self._attr_name is not None:
            clear_eager_relation(self._owner, self._attr_name)

    @property
    def _related_type(self) -> str:
        return get_morph_alias(self._related_model)

    @property
    def _owner_id(self) -> Any:
        return getattr(self._owner, self._owner_key)

    def _related_pk_col(self) -> Any:
        mapper = sa_inspect(self._related_model)
        if mapper is None:
            raise TypeError(f"{self._related_model} is not a mapped SQLAlchemy class")
        return mapper.primary_key[0]

    def _owner_where(self) -> tuple[Any, Any]:
        return (
            self._table.c[self._ofk] == self._owner_id,
            self._table.c[self._type_col] == self._related_type,
        )

    def __aiter__(self) -> AsyncIterator[T]:
        return self._iter_related()

    async def _iter_related(self) -> AsyncGenerator[T]:
        if self._attr_name is not None:
            cached = get_eager_relation(self._owner, self._attr_name)
            if cached is not None:
                for row in cached:
                    yield cast("T", row)
                return
        session = get_active_session()
        pk_col = self._related_pk_col()
        owner_pred, type_pred = self._owner_where()
        stmt = (
            select(self._related_model)
            .join(self._table, self._table.c[self._id_col] == sa_cast(pk_col, String))
            .where(owner_pred)
            .where(type_pred)
        )
        result = await session.execute(stmt)
        for row in result.scalars():
            yield row

    async def all(self) -> list[T]:
        """Return all related rows linked to this owner through the morph pivot."""
        return [row async for row in self]

    async def attach(self, related_id: int, **pivot_kwargs: Any) -> bool:
        """Insert pivot row. Returns True if new, False if already present."""
        session = get_active_session()
        owner_pred, type_pred = self._owner_where()
        check = (
            select(self._table)
            .where(owner_pred)
            .where(type_pred)
            .where(self._table.c[self._id_col] == str(related_id))
        )
        if (await session.execute(check)).fetchone() is not None:
            return False
        await session.execute(
            insert(self._table).values(
                **{
                    self._ofk: self._owner_id,
                    self._type_col: self._related_type,
                    self._id_col: str(related_id),
                    **pivot_kwargs,
                }
            )
        )
        await session.flush()
        self._invalidate_cache()
        return True

    async def detach(self, related_id: int) -> None:
        """Remove the pivot row for related_id. No-op if absent."""
        session = get_active_session()
        owner_pred, type_pred = self._owner_where()
        await session.execute(
            delete(self._table)
            .where(owner_pred)
            .where(type_pred)
            .where(self._table.c[self._id_col] == str(related_id))
        )
        await session.flush()
        self._invalidate_cache()

    async def _current_ids(self) -> set[int]:
        session = get_active_session()
        owner_pred, type_pred = self._owner_where()
        stmt = select(self._table.c[self._id_col]).where(owner_pred).where(type_pred)
        return {int(v) for v in (await session.execute(stmt)).scalars()}

    async def sync(self, related_ids: SyncIds) -> SyncResult:
        """Replace pivot rows so they match related_ids, returning what changed."""
        desired = normalize_sync_ids(related_ids)
        current_ids = await self._current_ids()
        result: SyncResult = {"attached": [], "detached": [], "updated": []}
        for rid in current_ids - set(desired):
            await self.detach(rid)
            result["detached"].append(rid)
        for rid, attrs in desired.items():
            if rid not in current_ids:
                await self.attach(rid, **attrs)
                result["attached"].append(rid)
        return result

    async def toggle(self, related_id: int) -> str:
        """Attach if absent, detach if present. Returns 'attached' or 'detached'."""
        if related_id in await self._current_ids():
            await self.detach(related_id)
            return "detached"
        await self.attach(related_id)
        return "attached"


class MorphedByMany(Generic[T]):
    """Inverse-side descriptor for a polymorphic many-to-many relation.

    Declared on the model that the pivot's ``{name}_type``/``{name}_id`` point at
    from the *other* direction. Mirrors Laravel's ``morphedByMany``::

        class Tag(Model):
            posts: ClassVar[MorphedByMany[Post]] = MorphedByMany(
                Post, table=taggables, name="taggable", related_key="tag_id"
            )
    """

    def __init__(
        self,
        related_model: type[T] | Callable[[], type[T]],
        *,
        table: Table,
        name: str,
        related_key: str,
    ) -> None:
        # Inverse relations commonly point at a model defined later in the module,
        # so accept a `lambda: Model` thunk and resolve it lazily.
        self._related_ref = related_model
        self._resolved: type[T] | None = None
        self._table = table
        self._name = name
        self._type_col = f"{name}_type"
        self._id_col = f"{name}_id"
        self._ofk = related_key
        self._attr_name: str | None = None

    def __set_name__(self, owner: type[Any], name: str) -> None:
        self._attr_name = name

    @property
    def table(self) -> Table:
        return self._table

    @property
    def related_model(self) -> type[T]:
        if self._resolved is None:
            ref = self._related_ref
            self._resolved = ref() if callable(ref) and not isinstance(ref, type) else ref
        return self._resolved

    @property
    def name(self) -> str:
        return self._name

    def link_spec(self) -> MorphedByManyLink:
        related = self.related_model
        return MorphedByManyLink(
            table=self._table,
            related_model=related,
            type_column=self._type_col,
            id_column=self._id_col,
            owner_foreign_key=self._ofk,
            related_type=get_morph_alias(related),
        )

    @overload
    def __get__(self, obj: None, objtype: type) -> MorphedByMany[T]: ...

    @overload
    def __get__(self, obj: Any, objtype: type) -> MorphedByManyAccessor[T]: ...

    def __get__(
        self, obj: Any, objtype: type | None = None
    ) -> MorphedByMany[T] | MorphedByManyAccessor[T]:
        if obj is None:
            return self
        return MorphedByManyAccessor(
            owner=obj,
            related_model=self.related_model,
            table=self._table,
            type_column=self._type_col,
            id_column=self._id_col,
            owner_foreign_key=self._ofk,
            attr_name=self._attr_name,
        )
