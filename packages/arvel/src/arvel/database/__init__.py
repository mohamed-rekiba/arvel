"""Arvent — Arvel's Eloquent-style ORM built on SQLAlchemy.

Public surface frozen for 0.x. See ``docs/api/database-api.md`` for the
full contract.
"""

from __future__ import annotations

from arvel.database.attributes import Attribute, CastsAttributes, accessor, mutator
from arvel.database.casts import DecryptionError, EncryptedType, EnumType, PydanticType
from arvel.database.collection import ModelCollection
from arvel.database.columns import (
    big_integer,
    boolean,
    column,
    datetime,
    decimal,
    enum,
    field,
    foreign_id,
    foreign_string,
    foreign_uuid,
    id_,
    integer,
    json,
    jsonb,
    nullable_column,
    string,
    text,
    tsvector,
    uuid,
    uuid_id,
)
from arvel.database.db import DB, TableQueryBuilder
from arvel.database.domain import DomainService
from arvel.database.events import ModelEvent, Observer, fire_after_commit
from arvel.database.exceptions import (
    DatabaseConnectionError,
    MassAssignmentError,
    MigrationNotReversibleError,
    ModelNotFoundError,
    MultipleResultsError,
    OperationCancelledError,
    OutsideTransactionError,
    ReadModelNotFoundError,
    ReadOnlyModelError,
    RelationNotLoadedError,
    UnknownRelationError,
)
from arvel.database.factories import Factory
from arvel.database.migrations import Migration
from arvel.database.mixins import PublishableMixin, TranslatableMixin, parse_trashed_mode
from arvel.database.model import (
    ActiveRecord,
    HasUlids,
    HasUuids,
    Model,
    Prunable,
    SoftDeletes,
    Timestamps,
    ViewModel,
)
from arvel.database.orm import (
    Ancestors,
    BelongsTo,
    Descendants,
    HasMany,
    HasOne,
    Mapped,
    MorphMapError,
    column_attr,
    declared_attr,
    foreign,
    mapped_column,
    morph_map,
    morph_map_required,
    relationship,
    require_morph_map,
)
from arvel.database.paginator import Paginator
from arvel.database.policy import (
    ImmutableReadModelError,
    ReadModelPolicy,
    ReadModelPolicyViolationError,
)
from arvel.database.query import CursorPaginator, QueryBuilder, SimplePaginator
from arvel.database.schema import Blueprint, ForeignKeyAction, IdType, Schema
from arvel.database.scope import GlobalScope, SoftDeleteScope, scope
from arvel.database.seeders import DatabaseSeeder, Seeder
from arvel.database.tree import TreeNode
from arvel.support.collections import Collection

__all__ = [
    "DB",
    "ActiveRecord",
    "Ancestors",
    "Attribute",
    "BelongsTo",
    "Blueprint",
    "CastsAttributes",
    "Collection",
    "CursorPaginator",
    "DatabaseConnectionError",
    "DatabaseSeeder",
    "DecryptionError",
    "Descendants",
    "DomainService",
    "EncryptedType",
    "EnumType",
    "Factory",
    "ForeignKeyAction",
    "GlobalScope",
    "HasMany",
    "HasOne",
    "HasUlids",
    "HasUuids",
    "IdType",
    "ImmutableReadModelError",
    "Mapped",
    "MassAssignmentError",
    "Migration",
    "MigrationNotReversibleError",
    "Model",
    "ModelCollection",
    "ModelEvent",
    "ModelNotFoundError",
    "MorphMapError",
    "MultipleResultsError",
    "Observer",
    "OperationCancelledError",
    "OutsideTransactionError",
    "Paginator",
    "Prunable",
    "PublishableMixin",
    "PydanticType",
    "QueryBuilder",
    "ReadModelNotFoundError",
    "ReadModelPolicy",
    "ReadModelPolicyViolationError",
    "ReadOnlyModelError",
    "RelationNotLoadedError",
    "Schema",
    "Seeder",
    "SimplePaginator",
    "SoftDeleteScope",
    "SoftDeletes",
    "TableQueryBuilder",
    "Timestamps",
    "TranslatableMixin",
    "TreeNode",
    "UnknownRelationError",
    "ViewModel",
    "accessor",
    "big_integer",
    "boolean",
    "column",
    "column_attr",
    "datetime",
    "decimal",
    "declared_attr",
    "enum",
    "field",
    "fire_after_commit",
    "foreign",
    "foreign_id",
    "foreign_string",
    "foreign_uuid",
    "id_",
    "integer",
    "json",
    "jsonb",
    "mapped_column",
    "morph_map",
    "morph_map_required",
    "mutator",
    "nullable_column",
    "parse_trashed_mode",
    "relationship",
    "require_morph_map",
    "scope",
    "string",
    "text",
    "tsvector",
    "uuid",
    "uuid_id",
]
