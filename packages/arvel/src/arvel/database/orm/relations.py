"""FK relation helpers: HasMany, HasOne, BelongsTo, HasManyThrough, HasOneThrough.

Each is a QueryBuilder subclass pre-scoped to a FK WHERE clause.

Also provides ``has_many_attr`` — a class-attribute declarator that wraps
``relationship()`` for viewonly one-to-many associations.  Kept in this module
(not ``orm/__init__.py``) so the init stays a re-export hub.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from sqlalchemy import inspect as sqla_inspect
from sqlalchemy import select
from sqlalchemy.orm import Mapped, Mapper, declared_attr, relationship

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


class HasMany(QueryBuilder[T], Generic[T]):
    """QueryBuilder[T] pre-scoped to WHERE foreign_key = owner_pk."""

    def __init__(
        self,
        model: type[T],
        stmt: Any = None,
        *,
        owner: Any = None,
        fk_col: str | None = None,
        owner_pk: Any = None,
    ) -> None:
        super().__init__(model, stmt)
        self._owner = owner
        self._fk_col = fk_col
        self._owner_pk = owner_pk

    def _clone(self, stmt: Any = None) -> HasMany[T]:
        new = super()._clone(stmt)
        new._owner = self._owner
        new._fk_col = self._fk_col
        new._owner_pk = self._owner_pk
        return new

    async def save(self, instance: Any) -> Any:
        """Set the FK on the instance to this owner's PK and persist."""
        if self._fk_col:
            setattr(instance, self._fk_col, self._owner_pk)
        session = get_active_session()
        session.add(instance)
        await session.flush()
        return instance

    async def create(self, attrs: dict[str, Any]) -> Any:
        """Create a new related instance with the FK already set."""
        if self._fk_col:
            attrs = {**attrs, self._fk_col: self._owner_pk}
        return await self._model.create(**attrs)


class HasOne(QueryBuilder[T], Generic[T]):
    """QueryBuilder[T] pre-scoped to WHERE foreign_key = owner_pk, limit 1."""

    def __init__(
        self,
        model: type[T],
        stmt: Any = None,
        *,
        owner: Any = None,
        fk_col: str | None = None,
        owner_pk: Any = None,
    ) -> None:
        super().__init__(model, stmt)
        self._owner = owner
        self._fk_col = fk_col
        self._owner_pk = owner_pk

    def _clone(self, stmt: Any = None) -> HasOne[T]:
        new = super()._clone(stmt)
        new._owner = self._owner
        new._fk_col = self._fk_col
        new._owner_pk = self._owner_pk
        return new

    async def save(self, instance: Any) -> Any:
        if self._fk_col:
            setattr(instance, self._fk_col, self._owner_pk)
        session = get_active_session()
        session.add(instance)
        await session.flush()
        return instance

    async def create(self, attrs: dict[str, Any]) -> Any:
        if self._fk_col:
            attrs = {**attrs, self._fk_col: self._owner_pk}
        return await self._model.create(**attrs)


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
    ) -> None:
        super().__init__(model, stmt)
        self._owner = owner
        self._fk_attr = fk_attr
        self._owner_key = owner_key

    def _clone(self, stmt: Any = None) -> BelongsTo[T]:
        new = super()._clone(stmt)
        new._owner = self._owner
        new._fk_attr = self._fk_attr
        new._owner_key = self._owner_key
        return new

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


class _HasManyAttr:
    """Descriptor sentinel for ``has_many_attr``.

    Replaces itself with a ``declared_attr``-wrapped relationship during class
    creation (via ``__set_name__``), so ``MappedAsDataclass`` never sees the
    attribute in ``__annotations__`` and never includes it in ``__init__``.
    """

    __slots__ = ("_fk", "_local_pk", "_target")

    def __init__(self, target: str, fk: str, local_pk: str = "id") -> None:
        self._target = target
        self._fk = fk
        self._local_pk = local_pk

    def __set_name__(self, owner: type[Any], name: str) -> None:
        target = self._target
        fk = self._fk
        local_pk = self._local_pk

        def _rel(cls: type[Any]) -> Any:
            # String-form join deferred to the SA mapper registry — safe with
            # circular model imports because SA resolves strings lazily.
            join_expr = f"foreign({target}.{fk}) == {cls.__name__}.{local_pk}"
            return relationship(
                target,
                primaryjoin=join_expr,
                uselist=True,
                init=False,
                viewonly=True,
                lazy="raise_on_sql",
            )

        _rel.__annotations__["return"] = Mapped[list[Any]]
        # Install the real declared_attr and erase the annotation so that
        # MappedAsDataclass does not treat this as a dataclass field.
        setattr(owner, name, declared_attr(_rel))
        owner.__annotations__.pop(name, None)

    def __get__(self, obj: Any, objtype: Any = None) -> _HasManyAttr:
        # Defensive fallback — should never be reached after __set_name__.
        return self


def has_many_attr(
    target: str,
    *,
    fk: str,
    local_pk: str = "id",
) -> Any:
    """Class-attribute declarator for a viewonly has-many ORM relationship.

    Works with any annotation; the annotation is removed from the class before
    ``MappedAsDataclass`` processes it, so the attribute is never included in
    ``__init__``::

        catalog_products: list[Any] = has_many_attr("ProductCatalog", fk="category_id")

    Usable with ``where_has`` / ``doesnt_have`` / ``has``::

        Category.where_has(Category.catalog_products, lambda q: q.where(...))

    Accessing the attribute on an unloaded instance raises
    ``sqlalchemy.exc.InvalidRequestError`` instead of issuing a silent lazy
    query (``lazy="raise_on_sql"``).
    """
    return _HasManyAttr(target, fk=fk, local_pk=local_pk)


__all__ = [
    "BelongsTo",
    "HasMany",
    "HasManyThrough",
    "HasOne",
    "HasOneThrough",
    "_HasManyAttr",
    "has_many_attr",
]
