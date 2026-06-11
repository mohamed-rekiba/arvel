"""FK relation helpers: HasMany, HasOne, BelongsTo, HasManyThrough, HasOneThrough.

Each is a QueryBuilder subclass pre-scoped to a FK WHERE clause. Defined as
zero-arg accessor methods on a model (``def orders(self) -> HasMany[Order]``),
they power lazy queries, eager loading (``with_("orders")``), cached read-back,
and ``where_has`` / ``with_count`` from a single declaration.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast

from sqlalchemy import inspect as sqla_inspect
from sqlalchemy import literal, select
from sqlalchemy.orm import Mapper, aliased

from arvel.database.orm._eager import get_eager_relation
from arvel.database.query import QueryBuilder
from arvel.database.session import autocommit, get_active_session
from arvel.database.tree import TreeNode, assemble_forest

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


@dataclass(frozen=True, slots=True)
class RecursiveLink:
    """Resolved shape of a self-referential recursive relation.

    ``direction`` is ``"descendants"`` (walk down via ``parent_key``) or
    ``"ancestors"`` (walk up). The eager engine reads this to seed one batched
    adjacency CTE across every parent.
    """

    related_model: type[Any]
    direction: str
    id_key: str
    parent_key: str
    name: str
    max_depth: int | None


def build_adjacency_cte(
    model: type[Any],
    *,
    id_key: str,
    parent_key: str,
    direction: str,
    roots: Sequence[Any],
    max_depth: int | None,
    base_where: Any = None,
) -> Any:
    """Build a recursive adjacency-list CTE seeded by *roots*.

    The CTE carries ``_node_id``, ``_parent_id``, ``_root_id`` (the seeding row a
    node descends from / leads up to) and ``_tree_depth`` (1 at the first hop).
    ``_root_id`` is what lets eager loading fan a single query's rows back to the
    right parent. ``base_where`` (global scopes + caller constraint) is applied to
    both members, so a soft-deleted node prunes its branch.
    """
    id_attr = getattr(model, id_key)
    parent_attr = getattr(model, parent_key)
    # __tablename__ is guaranteed on every model; the variable dodges B009's
    # "use attribute access" rule (the attr isn't statically known on the class).
    _tbl_attr = "__tablename__"
    table_name: str = getattr(model, _tbl_attr)
    cte_name = f"{table_name}_adjacency"

    if direction == "descendants":
        anchor = select(
            id_attr.label("_node_id"),
            parent_attr.label("_parent_id"),
            parent_attr.label("_root_id"),
            literal(1).label("_tree_depth"),
        ).where(parent_attr.in_(roots))
        if base_where is not None:
            anchor = anchor.where(base_where)
        cte = anchor.cte(cte_name, recursive=True)
        recursive = select(
            id_attr.label("_node_id"),
            parent_attr.label("_parent_id"),
            cte.c._root_id.label("_root_id"),
            (cte.c._tree_depth + 1).label("_tree_depth"),
        ).join(cte, parent_attr == cte.c._node_id)
        if max_depth is not None:
            recursive = recursive.where(cte.c._tree_depth < max_depth)
        if base_where is not None:
            recursive = recursive.where(base_where)
        return cte.union_all(recursive)

    root_alias = aliased(model, name="_adjacency_root")
    root_id_attr = getattr(root_alias, id_key)
    root_parent_attr = getattr(root_alias, parent_key)
    anchor = (
        select(
            id_attr.label("_node_id"),
            parent_attr.label("_parent_id"),
            root_id_attr.label("_root_id"),
            literal(1).label("_tree_depth"),
        )
        .select_from(model)
        .join(root_alias, root_parent_attr == id_attr)
        .where(root_id_attr.in_(roots))
    )
    if base_where is not None:
        anchor = anchor.where(base_where)
    cte = anchor.cte(cte_name, recursive=True)
    recursive = select(
        id_attr.label("_node_id"),
        parent_attr.label("_parent_id"),
        cte.c._root_id.label("_root_id"),
        (cte.c._tree_depth + 1).label("_tree_depth"),
    ).join(cte, id_attr == cte.c._parent_id)
    if max_depth is not None:
        recursive = recursive.where(cte.c._tree_depth < max_depth)
    if base_where is not None:
        recursive = recursive.where(base_where)
    return cte.union_all(recursive)


class _Recursive(QueryBuilder[T], Generic[T]):
    """Self-referential recursive relation builder (descendants / ancestors).

    Lazy ``.get()`` returns the flat subtree as a ModelCollection; ``.as_tree()``
    returns a TreeNode forest. ``with_tree(...)`` eager-loads it in one query and
    both terminals then serve from the per-owner cache. Chained ``.where(...)``
    filters the walk at every level.
    """

    _direction: str = "descendants"

    def __init__(
        self,
        model: type[T],
        stmt: Any = None,
        *,
        owner: Any = None,
        owner_pk: Any = None,
        id_key: str = "id",
        parent_key: str = "parent_id",
        max_depth: int | None = None,
    ) -> None:
        super().__init__(model, stmt)
        self._owner = owner
        self._owner_pk = owner_pk
        self._id_key = id_key
        self._parent_key = parent_key
        self._max_depth = max_depth
        self._relation_name: str | None = None

    def _clone(self, stmt: Any = None) -> Any:
        new = super()._clone(stmt)
        new._owner = self._owner
        new._owner_pk = self._owner_pk
        new._id_key = self._id_key
        new._parent_key = self._parent_key
        new._max_depth = self._max_depth
        new._relation_name = self._relation_name
        return new

    def with_max_depth(self, depth: int) -> Any:
        """Cap the walk to *depth* hops (1 = direct children/parent)."""
        clone = self._clone()
        clone._max_depth = depth
        return clone

    def link_spec(self, name: str) -> RecursiveLink:
        """Resolved shape for the eager engine."""
        return RecursiveLink(
            self._model, self._direction, self._id_key, self._parent_key, name, self._max_depth
        )

    def _base_where(self) -> Any:
        # Folds global scopes (soft deletes) and any chained .where() into one
        # predicate over the model's columns, applied to both CTE members.
        return self.apply_global_scopes().whereclause

    @autocommit(write=False)
    async def _fetch_rows(self, roots: Iterable[Any]) -> list[Any]:
        distinct = [r for r in roots if r is not None]
        if not distinct:
            return []
        full_cte = build_adjacency_cte(
            self._model,
            id_key=self._id_key,
            parent_key=self._parent_key,
            direction=self._direction,
            roots=distinct,
            max_depth=self._max_depth,
            base_where=self._base_where(),
        )
        id_attr = getattr(self._model, self._id_key)
        stmt = (
            select(self._model, full_cte.c._root_id, full_cte.c._tree_depth)
            .join(full_cte, id_attr == full_cte.c._node_id)
            .order_by(full_cte.c._tree_depth)
        )
        result = await get_active_session().execute(stmt)
        return list(result.all())

    def _cached(self) -> list[Any] | None:
        if self._owner is not None and self._relation_name is not None:
            return get_eager_relation(self._owner, self._relation_name)
        return None

    async def all(self) -> Any:
        from arvel.database.collection import ModelCollection

        cached = self._cached()
        if cached is not None:
            return ModelCollection(list(cached))
        rows = await self._fetch_rows([self._owner_pk])
        nodes: list[Any] = [row[0] for row in rows]
        return ModelCollection(nodes)

    async def as_tree(self) -> list[TreeNode[T]]:
        """Assemble the walked rows into a TreeNode forest (roots = first hop)."""
        cached = self._cached()
        if cached is not None:
            nodes = list(cached)
        else:
            rows = await self._fetch_rows([self._owner_pk])
            nodes = [row[0] for row in rows]
        return assemble_forest(nodes, id_key=self._id_key, parent_key=self._parent_key)


class Descendants(_Recursive[T], Generic[T]):
    """All rows below the owner, found by walking ``parent_key`` downward."""

    _direction = "descendants"


class Ancestors(_Recursive[T], Generic[T]):
    """All rows above the owner, found by walking ``parent_key`` upward."""

    _direction = "ancestors"


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

    @autocommit(write=False)
    async def all(self) -> Any:
        from arvel.support.collections import Collection

        result = await get_active_session().execute(self.apply_global_scopes())
        return Collection(result.scalars().all())


class HasOneThrough(HasManyThrough[T], Generic[T]):
    """HasOne via an intermediate model."""

    @autocommit(write=False)
    async def first(self) -> T | None:
        stmt = self.apply_global_scopes().limit(1)
        result = await get_active_session().execute(stmt)
        return result.scalars().first()


__all__ = [
    "Ancestors",
    "BelongsTo",
    "Descendants",
    "FkMethodLink",
    "HasMany",
    "HasManyThrough",
    "HasOne",
    "HasOneThrough",
    "RecursiveLink",
    "build_adjacency_cte",
]
