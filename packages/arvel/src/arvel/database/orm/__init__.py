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
from arvel.database.orm.has_one_of_many import (
    HasOneOfMany,
    HasOneOfManyAccessor,
    HasOneOfManyLink,
)
from arvel.database.orm.morph import (
    MorphChildLink,
    MorphMany,
    MorphManyAccessor,
    MorphOne,
    MorphOneAccessor,
    MorphTo,
    MorphToAccessor,
)
from arvel.database.orm.morph_map import (
    MorphMapError,
    get_morph_alias,
    morph_map,
    morph_map_required,
    require_morph_map,
    reset_morph_map,
    resolve_morph_class,
)
from arvel.database.orm.morph_to_many import (
    MorphedByMany,
    MorphedByManyAccessor,
    MorphedByManyLink,
    MorphToMany,
    MorphToManyAccessor,
    MorphToManyLink,
)
from arvel.database.orm.relations import BelongsTo, FkMethodLink, HasMany, HasOne

__all__ = [
    "BelongsTo",
    "BelongsToMany",
    "BelongsToManyAccessor",
    "FkMethodLink",
    "HasMany",
    "HasOne",
    "HasOneOfMany",
    "HasOneOfManyAccessor",
    "HasOneOfManyLink",
    "Mapped",
    "MorphChildLink",
    "MorphMany",
    "MorphManyAccessor",
    "MorphMapError",
    "MorphOne",
    "MorphOneAccessor",
    "MorphTo",
    "MorphToAccessor",
    "MorphToMany",
    "MorphToManyAccessor",
    "MorphToManyLink",
    "MorphedByMany",
    "MorphedByManyAccessor",
    "MorphedByManyLink",
    "column_attr",
    "declared_attr",
    "foreign",
    "get_morph_alias",
    "mapped_column",
    "morph_map",
    "morph_map_required",
    "relationship",
    "require_morph_map",
    "reset_morph_map",
    "resolve_morph_class",
]
