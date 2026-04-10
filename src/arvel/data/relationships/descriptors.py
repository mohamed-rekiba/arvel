"""Relationship descriptor functions and metadata containers.

Each helper (has_one, has_many, belongs_to, belongs_to_many) returns a
RelationshipDescriptor that the HasRelationships mixin replaces with a real
SA relationship() before the mapper processes the class.

The descriptor implements the Python descriptor protocol (``__get__``) so
that static type checkers see the resolved model type instead of
``RelationshipDescriptor``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Literal, overload

ComparisonOperator = Literal[">", ">=", "<", "<=", "=", "!="]


class RelationType(Enum):
    HAS_ONE = auto()
    HAS_MANY = auto()
    BELONGS_TO = auto()
    BELONGS_TO_MANY = auto()


@dataclass(frozen=True)
class RelationshipDescriptor:
    """Immutable metadata about a declared relationship.

    Stored in the model's __relationship_registry__ for introspection.
    At runtime, ``HasRelationships.__init_subclass__`` replaces these with
    SA ``relationship()`` objects, so ``__get__`` is never actually called
    on a configured model.  The ``__get__`` exists purely for static type
    checkers.
    """

    related_model: type | str
    relation_type: RelationType
    foreign_key: str | None = None
    local_key: str | None = None
    back_populates: str | None = None
    pivot_table: str | None = None
    pivot_fields: list[str] = field(default_factory=list)


class _HasOneDescriptor(RelationshipDescriptor):
    """Typed descriptor for has_one relationships (T | None at the type level)."""

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        return self  # pragma: no cover — replaced by SA at class init


class _HasManyDescriptor(RelationshipDescriptor):
    """Typed descriptor for has_many / belongs_to_many (list[T] at the type level)."""

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        return self  # pragma: no cover — replaced by SA at class init


class _BelongsToDescriptor(RelationshipDescriptor):
    """Typed descriptor for belongs_to relationships (T at the type level)."""

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        return self  # pragma: no cover — replaced by SA at class init


# ──────────────────────────────────────────────────────────
#  Public helpers with typed overloads
# ──────────────────────────────────────────────────────────


@overload
def has_one[T](
    related: type[T],
    *,
    foreign_key: str | None = ...,
    local_key: str | None = ...,
    back_populates: str | None = ...,
) -> T: ...


@overload
def has_one(
    related: str,
    *,
    foreign_key: str | None = ...,
    local_key: str | None = ...,
    back_populates: str | None = ...,
) -> Any: ...


def has_one(
    related: type | str,
    *,
    foreign_key: str | None = None,
    local_key: str | None = None,
    back_populates: str | None = None,
) -> Any:
    """Declare a one-to-one relationship where the FK lives on the related model.

    Convention: FK on the related table is ``{owner_tablename}_id``.
    """
    return _HasOneDescriptor(
        related_model=related,
        relation_type=RelationType.HAS_ONE,
        foreign_key=foreign_key,
        local_key=local_key,
        back_populates=back_populates,
    )


@overload
def has_many[T](
    related: type[T],
    *,
    foreign_key: str | None = ...,
    local_key: str | None = ...,
    back_populates: str | None = ...,
) -> list[T]: ...


@overload
def has_many(
    related: str,
    *,
    foreign_key: str | None = ...,
    local_key: str | None = ...,
    back_populates: str | None = ...,
) -> Any: ...


def has_many(
    related: type | str,
    *,
    foreign_key: str | None = None,
    local_key: str | None = None,
    back_populates: str | None = None,
) -> Any:
    """Declare a one-to-many relationship where the FK lives on the related model.

    Convention: FK on the related table is ``{owner_tablename}_id``.
    """
    return _HasManyDescriptor(
        related_model=related,
        relation_type=RelationType.HAS_MANY,
        foreign_key=foreign_key,
        local_key=local_key,
        back_populates=back_populates,
    )


@overload
def belongs_to[T](
    related: type[T],
    *,
    foreign_key: str | None = ...,
    local_key: str | None = ...,
    back_populates: str | None = ...,
) -> T: ...


@overload
def belongs_to(
    related: str,
    *,
    foreign_key: str | None = ...,
    local_key: str | None = ...,
    back_populates: str | None = ...,
) -> Any: ...


def belongs_to(
    related: type | str,
    *,
    foreign_key: str | None = None,
    local_key: str | None = None,
    back_populates: str | None = None,
) -> Any:
    """Declare the inverse of has_one/has_many — the FK lives on *this* model.

    Convention: FK column on this table is ``{related_tablename}_id``.
    """
    return _BelongsToDescriptor(
        related_model=related,
        relation_type=RelationType.BELONGS_TO,
        foreign_key=foreign_key,
        local_key=local_key,
        back_populates=back_populates,
    )


@overload
def belongs_to_many[T](
    related: type[T],
    *,
    pivot_table: str | None = ...,
    foreign_key: str | None = ...,
    related_key: str | None = ...,
    pivot_fields: list[str] | None = ...,
    back_populates: str | None = ...,
) -> list[T]: ...


@overload
def belongs_to_many(
    related: str,
    *,
    pivot_table: str | None = ...,
    foreign_key: str | None = ...,
    related_key: str | None = ...,
    pivot_fields: list[str] | None = ...,
    back_populates: str | None = ...,
) -> Any: ...


def belongs_to_many(
    related: type | str,
    *,
    pivot_table: str | None = None,
    foreign_key: str | None = None,
    related_key: str | None = None,
    pivot_fields: list[str] | None = None,
    back_populates: str | None = None,
) -> Any:
    """Declare a many-to-many relationship through a pivot (association) table.

    Conventions:
    - Pivot table: alphabetical join of both table names (e.g. ``role_user``).
    - FK columns: ``{table}_id`` for each side.
    """
    return _HasManyDescriptor(
        related_model=related,
        relation_type=RelationType.BELONGS_TO_MANY,
        foreign_key=foreign_key,
        local_key=related_key,
        back_populates=back_populates,
        pivot_table=pivot_table,
        pivot_fields=pivot_fields or [],
    )
