"""FK relation helpers: HasMany, HasOne, BelongsTo, HasManyThrough, HasOneThrough.

Each is a QueryBuilder subclass pre-scoped to a FK WHERE clause. Defined as
zero-arg accessor methods on a model (``def orders(self) -> HasMany[Order]``),
they power lazy queries, eager loading (``with_("orders")``), cached read-back,
and ``where_has`` / ``with_count`` from a single declaration.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast

from sqlalchemy import inspect as sqla_inspect
from sqlalchemy import select
from sqlalchemy.orm import Mapper

from arvel.database.orm._eager import get_eager_relation
from arvel.database.query import QueryBuilder
from arvel.database.session import get_active_session

if TYPE_CHECKING:
    from arvel.database.model import Model

T = TypeVar("T", bound="Model")


@dataclass(frozen=True, slots=True)
class ThroughSpec:
    """Configuration for a ``HasManyThrough`` / ``HasOneThrough`` join."""

    owner_cls: type[Any]
    through: type[Any]
    fk1: str = ""
    fk2: str = ""
    local_key: str = "id"


@dataclass(frozen=True, slots=True)
class FkMethodLink:
    """Resolved shape of a method-style FK relation (``has_many``/``has_one``/``belongs_to``).

    The eager engine reads this to batch-load and to build ``where_has``/``has``
    subqueries. ``related_col`` and ``local_col`` name the two sides of the join:
    rows match where ``related.<related_col> == owner.<local_col>``.
    """

    related_model: type[Any]
    direction: str  # "has_many" | "has_one" | "belongs_to"
    related_col: str
    local_col: str
    name: str


class _OfMany(QueryBuilder[T], Generic[T]):
    """Shared `latest_of_many` / `oldest_of_many` / `of_many` for HasMany/HasOne.

    Returns the single related row that wins an aggregate (MAX/MIN of a column),
    with the PK as a deterministic tiebreaker — Laravel's `latestOfMany`/`ofMany`.
    """

    def _pk_name(self) -> str:
        key = sqla_inspect(self._model).primary_key[0].key
        if key is None:
            raise TypeError(f"{self._model.__name__} primary key column has no key")
        return key

    async def of_many(self, column: str = "created_at", aggregate: str = "max") -> T | None:
        """Return the related row with MAX (default) or MIN of *column*."""
        pk = self._pk_name()
        if aggregate.lower() == "max":
            scoped = self.order_by(f"-{column}", f"-{pk}")
        else:
            scoped = self.order_by(column, pk)
        return await scoped.first()

    async def latest_of_many(self, column: str = "created_at") -> T | None:
        return await self.of_many(column, "max")

    async def oldest_of_many(self, column: str = "created_at") -> T | None:
        return await self.of_many(column, "min")


class HasMany(_OfMany[T], Generic[T]):
    """QueryBuilder[T] pre-scoped to WHERE foreign_key = owner_pk."""

    def __init__(
        self,
        model: type[T],
        stmt: Any = None,
        *,
        owner: Any = None,
        fk_col: str | None = None,
        owner_pk: Any = None,
        local_key: str | None = None,
    ) -> None:
        super().__init__(model, stmt)
        self._owner = owner
        self._fk_col = fk_col
        self._owner_pk = owner_pk
        self._local_key = local_key
        # Set by the metaclass relation-method wrapper; lets terminal ops serve
        # eager-loaded results from the owner's cache instead of re-querying.
        self._relation_name: str | None = None

    def _clone(self, stmt: Any = None) -> HasMany[T]:
        new = super()._clone(stmt)
        new._owner = self._owner
        new._fk_col = self._fk_col
        new._owner_pk = self._owner_pk
        new._local_key = self._local_key
        new._relation_name = self._relation_name
        return new

    async def all(self) -> Any:
        if self._owner is not None and self._relation_name is not None:
            cached = get_eager_relation(self._owner, self._relation_name)
            if cached is not None:
                from arvel.database.collection import ModelCollection

                rows: list[Any] = list(cached)
                return ModelCollection(rows)
        return await super().all()

    def link_spec(self, name: str) -> FkMethodLink:
        """Resolved join shape for the eager engine and where_has/has subqueries."""
        if self._fk_col is None or self._local_key is None:
            raise TypeError(f"{type(self).__name__} relation is missing fk/local key")
        return FkMethodLink(self._model, "has_many", self._fk_col, self._local_key, name)

    async def save(self, instance: Any) -> Any:
        """Set the FK on the instance to this owner's PK and persist through the model."""
        if self._fk_col:
            setattr(instance, self._fk_col, self._owner_pk)
        # Route through Model.save() so events, mutators, and timestamps all run.
        await instance.save()
        return instance

    async def create(self, attrs: dict[str, Any]) -> Any:
        """Create a new related instance with the FK already set."""
        if self._fk_col:
            attrs = {**attrs, self._fk_col: self._owner_pk}
        return await self._model.create(**attrs)

    async def save_many(self, instances: Sequence[Any]) -> list[Any]:
        """Persist several related instances, setting the FK on each."""
        return [await self.save(instance) for instance in instances]

    async def create_many(self, rows: Sequence[dict[str, Any]]) -> list[Any]:
        """Create several related instances with the FK already set."""
        return [await self.create(attrs) for attrs in rows]


class HasOne(_OfMany[T], Generic[T]):
    """QueryBuilder[T] pre-scoped to WHERE foreign_key = owner_pk, limit 1."""

    def __init__(
        self,
        model: type[T],
        stmt: Any = None,
        *,
        owner: Any = None,
        fk_col: str | None = None,
        owner_pk: Any = None,
        local_key: str | None = None,
    ) -> None:
        super().__init__(model, stmt)
        self._owner = owner
        self._fk_col = fk_col
        self._owner_pk = owner_pk
        self._local_key = local_key
        self._relation_name: str | None = None

    def _clone(self, stmt: Any = None) -> HasOne[T]:
        new = super()._clone(stmt)
        new._owner = self._owner
        new._fk_col = self._fk_col
        new._owner_pk = self._owner_pk
        new._local_key = self._local_key
        new._relation_name = self._relation_name
        return new

    async def first(self) -> T | None:
        if self._owner is not None and self._relation_name is not None:
            cached = get_eager_relation(self._owner, self._relation_name)
            if cached is not None:
                return cast("T | None", cached[0]) if cached else None
        return await super().first()

    def link_spec(self, name: str) -> FkMethodLink:
        """Resolved join shape for the eager engine and where_has/has subqueries."""
        if self._fk_col is None or self._local_key is None:
            raise TypeError(f"{type(self).__name__} relation is missing fk/local key")
        return FkMethodLink(self._model, "has_one", self._fk_col, self._local_key, name)

    async def save(self, instance: Any) -> Any:
        if self._fk_col:
            setattr(instance, self._fk_col, self._owner_pk)
        # Route through Model.save() so events, mutators, and timestamps all run.
        await instance.save()
        return instance

    async def create(self, attrs: dict[str, Any]) -> Any:
        if self._fk_col:
            attrs = {**attrs, self._fk_col: self._owner_pk}
        return await self._model.create(**attrs)


_UNSET: Any = object()


class BelongsTo(QueryBuilder[T], Generic[T]):
    """QueryBuilder[T] pre-scoped to WHERE pk = owner.fk_value."""

    def __init__(
        self,
        model: type[T],
        stmt: Any = None,
        *,
        owner: Any = None,
        fk_attr: str | None = None,
        owner_key: str = "id",
        fk_present: bool = True,
    ) -> None:
        super().__init__(model, stmt)
        self._owner = owner
        self._fk_attr = fk_attr
        self._owner_key = owner_key
        # False when the owner's FK is null — first() must not match an arbitrary row.
        self._fk_present = fk_present
        self._default: Any = _UNSET
        self._relation_name: str | None = None

    def _clone(self, stmt: Any = None) -> BelongsTo[T]:
        new = super()._clone(stmt)
        new._owner = self._owner
        new._fk_attr = self._fk_attr
        new._owner_key = self._owner_key
        new._fk_present = self._fk_present
        new._default = self._default
        new._relation_name = self._relation_name
        return new

    def with_default(
        self,
        attributes: Mapping[str, Any] | Callable[[T, Any], None] | bool = True,
    ) -> BelongsTo[T]:
        """Return a default related model instead of None when the FK is null/unmatched.

        Mirrors Eloquent's ``withDefault``: pass nothing for an empty instance, a
        dict of attributes, or a callback ``(instance, owner)`` to populate it.
        """
        clone = self._clone()
        clone._default = attributes
        return clone

    def _build_default(self) -> T | None:
        spec = self._default
        if spec is _UNSET or spec is False:
            return None
        instance = self._model()
        if isinstance(spec, Mapping):
            attrs = cast("Mapping[str, Any]", spec)
            for key, value in attrs.items():
                setattr(instance, key, value)
        elif callable(spec):
            spec(instance, self._owner)
        return instance

    async def first(self) -> T | None:
        if self._owner is not None and self._relation_name is not None:
            cached = get_eager_relation(self._owner, self._relation_name)
            if cached is not None:
                if cached:
                    return cast("T | None", cached[0])
                return self._build_default()
        if not self._fk_present:
            return self._build_default()
        result = await super().first()
        if result is None:
            return self._build_default()
        return result

    def link_spec(self, name: str) -> FkMethodLink:
        """Resolved join shape for the eager engine and where_has/has subqueries."""
        if self._fk_attr is None:
            raise TypeError(f"{type(self).__name__} relation is missing fk attribute")
        return FkMethodLink(self._model, "belongs_to", self._owner_key, self._fk_attr, name)

    async def associate(self, related: Any) -> None:
        """Set the FK on the owner instance to point to related.pk (no persist)."""
        if self._owner is not None and self._fk_attr is not None:
            pk_val = getattr(related, self._owner_key, None)
            setattr(self._owner, self._fk_attr, pk_val)

    async def dissociate(self) -> None:
        """Set the FK on the owner instance to None (no persist)."""
        if self._owner is not None and self._fk_attr is not None:
            setattr(self._owner, self._fk_attr, None)


class HasManyThrough(QueryBuilder[T], Generic[T]):
    """HasMany via an intermediate pivot/through model."""

    def __init__(
        self,
        model: type[T],
        stmt: Any = None,
        *,
        spec: ThroughSpec | None = None,
    ) -> None:
        super().__init__(model, stmt)
        self._spec = spec
        if spec is not None:
            self._setup_join()

    @staticmethod
    def _resolve_fk(
        host_cls: type[Any],
        host_mapper: Mapper[Any],
        target_table: str,
        explicit_attr: str,
    ) -> Any:
        """Resolve a FK column on ``host_cls`` that references ``target_table``.

        Honours an explicit ``fk1`` / ``fk2`` attribute name first, then falls
        back to SQLAlchemy FK inspection.
        """
        if explicit_attr:
            attr = getattr(host_cls, explicit_attr, None)
            if attr is not None:
                return attr
        for col in host_mapper.persist_selectable.columns:
            if any(fk.column.table.name == target_table for fk in col.foreign_keys):
                return col
        return None

    def _setup_join(self) -> None:
        """Build the two-JOIN SELECT: related ← through ← owner."""
        spec = self._spec
        if spec is None:
            return

        through_mapper: Mapper[Any] = sqla_inspect(spec.through)
        related_mapper: Mapper[Any] = sqla_inspect(self._model)
        owner_mapper: Mapper[Any] = sqla_inspect(spec.owner_cls)

        related_fk_col = self._resolve_fk(
            self._model, related_mapper, spec.through.__tablename__, spec.fk2
        )
        through_fk_col = self._resolve_fk(
            spec.through, through_mapper, spec.owner_cls.__tablename__, spec.fk1
        )
        if related_fk_col is None or through_fk_col is None:
            return

        through_pk_col: Any = through_mapper.primary_key[0]
        owner_local_col: Any = (
            getattr(spec.owner_cls, spec.local_key, None) or owner_mapper.primary_key[0]
        )

        self._stmt = (
            select(self._model)
            .join(spec.through, related_fk_col == through_pk_col)
            .join(spec.owner_cls, through_fk_col == owner_local_col)
        )

    async def all(self) -> Any:
        from arvel.support.collections import Collection

        result = await get_active_session().execute(self.apply_global_scopes())
        return Collection(result.scalars().all())


class HasOneThrough(HasManyThrough[T], Generic[T]):
    """HasOne via an intermediate model."""

    async def first(self) -> T | None:
        stmt = self.apply_global_scopes().limit(1)
        result = await get_active_session().execute(stmt)
        return result.scalars().first()


__all__ = [
    "BelongsTo",
    "FkMethodLink",
    "HasMany",
    "HasManyThrough",
    "HasOne",
    "HasOneThrough",
]
