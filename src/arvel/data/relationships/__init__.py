"""Declarative relationship helpers for ArvelModel.

Provides Laravel-style has_one, has_many, belongs_to, and belongs_to_many
with convention-based FK detection, pivot table management, and eager loading.
"""

from arvel.data.relationships.descriptors import (
    ComparisonOperator,
    RelationshipDescriptor,
    RelationType,
    belongs_to,
    belongs_to_many,
    has_many,
    has_one,
)
from arvel.data.relationships.mixin import HasRelationships, LazyLoadError
from arvel.data.relationships.pivot import PivotManager

__all__ = [
    "ComparisonOperator",
    "HasRelationships",
    "LazyLoadError",
    "PivotManager",
    "RelationType",
    "RelationshipDescriptor",
    "belongs_to",
    "belongs_to_many",
    "has_many",
    "has_one",
]
