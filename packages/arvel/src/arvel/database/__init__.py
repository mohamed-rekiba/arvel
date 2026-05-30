"""Arvent — Arvel's Eloquent-style ORM built on SQLAlchemy.

Public surface frozen for 0.x. See ``docs/api/database-api.md`` for the
full contract.
"""

from __future__ import annotations

from arvel.database.attributes import accessor, mutator
from arvel.database.casts import DecryptionError, EncryptedType, EnumType, PydanticType
from arvel.database.columns import (
    big_integer,
    boolean,
    datetime,
    decimal,
    enum,
    foreign_id,
    foreign_uuid,
    id_,
    integer,
    json,
    jsonb,
    string,
    text,
    tsvector,
    uuid,
    uuid_id,
)
from arvel.database.db import DB, TableQueryBuilder
from arvel.database.domain import DomainService
from arvel.database.events import Observer, fire_after_commit
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
from arvel.database.model import ActiveRecord, Model, Prunable, SoftDeletes, Timestamps, ViewModel
from arvel.database.orm import (
    Mapped,
    column_attr,
    declared_attr,
    foreign,
    has_many_attr,
    mapped_column,
    relationship,
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
from arvel.support.collections import Collection

__all__ = [
    "DB",
    "ActiveRecord",
    "Blueprint",
    "Collection",
    "CursorPaginator",
    "DatabaseConnectionError",
    "DatabaseSeeder",
    "DecryptionError",
    "DomainService",
    "EncryptedType",
    "EnumType",
    "Factory",
    "ForeignKeyAction",
    "GlobalScope",
    "IdType",
    "ImmutableReadModelError",
    "Mapped",
    "MassAssignmentError",
    "Migration",
    "MigrationNotReversibleError",
    "Model",
    "ModelNotFoundError",
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
    "UnknownRelationError",
    "ViewModel",
    "accessor",
    "big_integer",
    "boolean",
    "column_attr",
    "datetime",
    "decimal",
    "declared_attr",
    "enum",
    "fire_after_commit",
    "foreign",
    "foreign_id",
    "foreign_uuid",
    "has_many_attr",
    "id_",
    "integer",
    "json",
    "jsonb",
    "mapped_column",
    "mutator",
    "parse_trashed_mode",
    "relationship",
    "scope",
    "string",
    "text",
    "tsvector",
    "uuid",
    "uuid_id",
]
