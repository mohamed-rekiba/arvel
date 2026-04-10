"""HasRelationships mixin — converts descriptor declarations into SA relationship().

Mixed into ArvelModel *before* DeclarativeBase in MRO so that __init_subclass__
replaces RelationshipDescriptor placeholders with real SA relationship() objects
before the mapper processes the class.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from sqlalchemy import Column, ForeignKey, Integer, Table
from sqlalchemy.orm import relationship

if TYPE_CHECKING:
    from sqlalchemy import MetaData
    from sqlalchemy.orm import RelationshipProperty
    from sqlalchemy.types import TypeEngine

from arvel.data.relationships.descriptors import RelationshipDescriptor, RelationType
from arvel.logging import Log

_logger = Log.named("arvel.data.relationships.mixin")

_STRICT_DEFAULT = os.environ.get("ARVEL_STRICT_RELATIONS", "true").lower() in ("true", "1", "yes")


class LazyLoadError(Exception):
    """Raised when a relationship is accessed without prior eager loading in strict mode."""


class _RelationshipRegistry:
    """Stores metadata about declared relationships on a model class."""

    __slots__ = ("_descriptors",)

    def __init__(self) -> None:
        self._descriptors: dict[str, RelationshipDescriptor] = {}

    def register(self, name: str, descriptor: RelationshipDescriptor) -> None:
        self._descriptors[name] = descriptor

    def get(self, name: str) -> RelationshipDescriptor | None:
        return self._descriptors.get(name)

    def all(self) -> dict[str, RelationshipDescriptor]:
        return dict(self._descriptors)


@lru_cache(maxsize=128)
def _get_singular(cls: type) -> str:
    """Return the singular form for a model class.

    Checks for an explicit ``__singular__`` override first, then falls back
    to naive singularization of ``__tablename__``.  Models with irregular
    plurals (e.g. "people", "addresses") should set ``__singular__``.

    Cached per class — table names and ``__singular__`` are fixed after class creation.
    """
    explicit = getattr(cls, "__singular__", None)
    if explicit is not None:
        return explicit
    tablename = getattr(cls, "__tablename__", "")
    return _singularize(tablename)


@lru_cache(maxsize=256)
def _singularize(tablename: str) -> str:
    """Naive singularization: strip trailing 's'.

    Known limitation: fails on irregular plurals (e.g. "people", "addresses").
    Use ``__singular__`` on the model class to override.
    """
    if tablename.endswith("ses") or tablename.endswith("xes") or tablename.endswith("zes"):
        return tablename[:-2]
    if tablename.endswith("ies"):
        return tablename[:-3] + "y"
    if tablename.endswith("s") and not tablename.endswith("ss"):
        return tablename[:-1]
    return tablename


@lru_cache(maxsize=256)
def _convention_fk(tablename: str) -> str:
    """Return the conventional FK column name for a table: ``{singular}_id``."""
    return f"{_singularize(tablename)}_id"


@lru_cache(maxsize=128)
def _pivot_table_name(table_a: str, table_b: str) -> str:
    """Return the conventional pivot table name: alphabetical join of singular names."""
    names = sorted([_singularize(table_a), _singularize(table_b)])
    return "_".join(names)


def _get_pk_column(cls: type) -> tuple[str, TypeEngine[Any]]:
    """Return (pk_column_name, pk_column_type) for a model class.

    Falls back to ("id", Integer()) if the table isn't available yet.
    """
    table = getattr(cls, "__table__", None)
    if table is not None:
        for col in table.columns:
            if col.primary_key:
                return col.name, col.type
    return "id", Integer()


def _get_or_create_pivot_table(
    metadata: MetaData,
    pivot_name: str,
    owner_table: str,
    related_table: str,
    owner_fk: str,
    related_fk: str,
    extra_columns: list[str],
    *,
    owner_pk: str = "id",
    related_pk: str = "id",
    owner_pk_type: TypeEngine[Any] | None = None,
    related_pk_type: TypeEngine[Any] | None = None,
) -> Table:
    """Get an existing pivot table or create one in the metadata."""
    if pivot_name in metadata.tables:
        return metadata.tables[pivot_name]

    fk_type_owner: TypeEngine[Any] = owner_pk_type if owner_pk_type is not None else Integer()
    fk_type_related: TypeEngine[Any] = related_pk_type if related_pk_type is not None else Integer()

    columns: list[Column[Any]] = [
        Column(
            owner_fk,
            fk_type_owner,
            ForeignKey(f"{owner_table}.{owner_pk}"),
            primary_key=True,
        ),
        Column(
            related_fk,
            fk_type_related,
            ForeignKey(f"{related_table}.{related_pk}"),
            primary_key=True,
        ),
    ]
    for col_name in extra_columns:
        columns.append(Column(col_name, Integer, nullable=True))

    return Table(pivot_name, metadata, *columns)


class HasRelationships:
    """Mixin that enables declarative relationship helpers on ArvelModel subclasses.

    Replaces RelationshipDescriptor instances in the class namespace with proper
    SA relationship() objects before DeclarativeBase processes the class.

    Models with irregular plural table names should set ``__singular__`` to the
    singular form (e.g. ``__singular__ = "person"`` for ``__tablename__ = "people"``).
    """

    __relationship_registry__: _RelationshipRegistry
    __singular__: str | None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        if cls.__dict__.get("__abstract__"):
            super().__init_subclass__(**kwargs)
            return

        registry = _RelationshipRegistry()
        cls.__relationship_registry__ = registry

        descriptors: dict[str, RelationshipDescriptor] = {}
        for attr_name in list(cls.__dict__):
            attr_value = cls.__dict__[attr_name]
            if isinstance(attr_value, RelationshipDescriptor):
                descriptors[attr_name] = attr_value
                registry.register(attr_name, attr_value)

        for attr_name, desc in descriptors.items():
            rel_prop = _build_relationship(cls, attr_name, desc)
            if rel_prop is not None:
                type.__setattr__(cls, attr_name, rel_prop)

        super().__init_subclass__(**kwargs)

    @classmethod
    def get_relationships(cls) -> dict[str, RelationshipDescriptor]:
        """Return a dict of {name: RelationshipDescriptor} for all declared relationships."""
        reg = getattr(cls, "__relationship_registry__", None)
        if reg is None:
            return {}
        return reg.all()


def _build_relationship(
    cls: type, attr_name: str, desc: RelationshipDescriptor
) -> RelationshipProperty[Any] | None:
    """Convert a RelationshipDescriptor into an SA relationship() property."""
    related = desc.related_model

    if desc.relation_type == RelationType.HAS_ONE:
        return _build_forward(cls, desc, related, uselist=False)
    if desc.relation_type == RelationType.HAS_MANY:
        return _build_forward(cls, desc, related, uselist=True)
    if desc.relation_type == RelationType.BELONGS_TO:
        return _build_belongs_to(cls, desc, related)
    if desc.relation_type == RelationType.BELONGS_TO_MANY:
        return _build_belongs_to_many(cls, desc, related)
    return None


def _common_kwargs(desc: RelationshipDescriptor) -> dict[str, Any]:
    """Build the kwargs shared by all relationship types."""
    kwargs: dict[str, Any] = {"lazy": "noload"}
    if desc.back_populates:
        kwargs["back_populates"] = desc.back_populates
    return kwargs


def _resolve_fk_on_related(related: type | str, foreign_key: str) -> list[Any] | str:
    """Resolve a FK column reference on the related model."""
    if isinstance(related, str):
        return f"[{related}.{foreign_key}]"
    fk_attr = getattr(related, foreign_key, None)
    if fk_attr is not None:
        return [fk_attr]
    return f"[{related.__name__}.{foreign_key}]"


def _build_forward(
    cls: type,
    desc: RelationshipDescriptor,
    related: type | str,
    *,
    uselist: bool,
) -> RelationshipProperty[Any]:
    """Build a has_one or has_many relationship (FK on the related side)."""
    kwargs = _common_kwargs(desc)
    kwargs["uselist"] = uselist
    if desc.foreign_key:
        kwargs["foreign_keys"] = _resolve_fk_on_related(related, desc.foreign_key)
    return relationship(related, **kwargs)


def _build_belongs_to(
    cls: type, desc: RelationshipDescriptor, related: type | str
) -> RelationshipProperty[Any]:
    """Build a belongs_to relationship (FK on *this* model's side)."""
    kwargs = _common_kwargs(desc)
    kwargs["uselist"] = False
    if desc.foreign_key:
        fk_attr = getattr(cls, desc.foreign_key, None)
        if fk_attr is not None:
            kwargs["foreign_keys"] = [fk_attr]
        else:
            kwargs["foreign_keys"] = f"[{cls.__name__}.{desc.foreign_key}]"
    return relationship(related, **kwargs)


def _build_belongs_to_many(
    cls: type, desc: RelationshipDescriptor, related: type | str
) -> RelationshipProperty[Any]:
    """Build a many-to-many relationship through a pivot (secondary) table."""
    kwargs = _common_kwargs(desc)

    if desc.pivot_table:
        owner_tablename = getattr(cls, "__tablename__", None)
        if owner_tablename is not None:
            metadata = getattr(cls, "metadata", None)
            if metadata is not None and desc.pivot_table in metadata.tables:
                kwargs["secondary"] = metadata.tables[desc.pivot_table]
            else:
                kwargs["secondary"] = desc.pivot_table

    return relationship(related, **kwargs)
