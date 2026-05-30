"""ORM relation descriptors and SQLAlchemy ORM primitives.

Imports from here rather than directly from ``sqlalchemy.orm`` keep SQLAlchemy
an implementation detail of the framework::

    from arvel.database import column_attr, declared_attr, foreign, mapped_column, relationship
"""

from __future__ import annotations

from sqlalchemy.orm import (
    Mapped,
    declared_attr,
    foreign,
    mapped_column,
    relationship,
)

from arvel.database.orm._column_attr import column_attr
from arvel.database.orm.belongs_to_many import BelongsToMany, BelongsToManyAccessor
from arvel.database.orm.morph import MorphMany, MorphManyAccessor, MorphOne, MorphOneAccessor
from arvel.database.orm.relations import has_many_attr

__all__ = [
    "BelongsToMany",
    "BelongsToManyAccessor",
    "Mapped",
    "MorphMany",
    "MorphManyAccessor",
    "MorphOne",
    "MorphOneAccessor",
    "column_attr",
    "declared_attr",
    "foreign",
    "has_many_attr",
    "mapped_column",
    "relationship",
]
