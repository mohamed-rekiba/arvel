"""ORM relation descriptors and SQLAlchemy ORM primitives.

Imports from here rather than directly from ``sqlalchemy.orm`` keep SQLAlchemy
an implementation detail of the framework::

    from arvel.database import column_attr, declared_attr, foreign, mapped_column, relationship
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import (
    Mapped,
    declared_attr,
    foreign,
    mapped_column,
)
from sqlalchemy.orm import relationship as _sa_relationship

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
from arvel.database.orm.relations import (
    Ancestors,
    BelongsTo,
    Descendants,
    FkMethodLink,
    HasMany,
    HasOne,
    RecursiveLink,
)


def relationship(*args: Any, **kwargs: Any) -> Any:
    """Like SQLAlchemy's ``relationship()`` but typed ``Any``, so the plain
    annotation drives the type: ``posts: list[Post] = relationship(...)``.

    The model metaclass wraps the annotation in ``Mapped[list[Post]]`` at build
    time, exactly like the column helpers. Returns the real SQLAlchemy
    ``RelationshipProperty`` at runtime.
    """
    return _sa_relationship(*args, **kwargs)


__all__ = [
    "Ancestors",
    "BelongsTo",
    "BelongsToMany",
    "BelongsToManyAccessor",
    "Descendants",
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
    "RecursiveLink",
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
