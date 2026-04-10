"""Arvel data layer.

ORM, repositories, transactions, observers, migrations, seeders, views,
relationships, result types, collections, scopes, casts, soft deletes,
and polymorphic relationships.

Imports are lazy — submodules are loaded on first attribute access
to keep ``import arvel.data`` fast.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from alembic import op as op
    from sqlalchemy import BigInteger as BigInteger
    from sqlalchemy import Boolean as Boolean
    from sqlalchemy import Column as Column
    from sqlalchemy import DateTime as DateTime
    from sqlalchemy import Float as Float
    from sqlalchemy import Integer as Integer
    from sqlalchemy import Numeric as Numeric
    from sqlalchemy import String as String
    from sqlalchemy import Text as Text
    from sqlalchemy import Uuid as Uuid
    from sqlalchemy.orm import Mapped as Mapped
    from sqlalchemy.orm import mapped_column as mapped_column

    from arvel.data.accessors import accessor as accessor
    from arvel.data.accessors import mutator as mutator
    from arvel.data.casts import Caster as Caster
    from arvel.data.casts import EncryptedCaster as EncryptedCaster
    from arvel.data.casts import EnumCaster as EnumCaster
    from arvel.data.casts import JsonCaster as JsonCaster
    from arvel.data.collection import ArvelCollection as ArvelCollection
    from arvel.data.collection import collect as collect
    from arvel.data.config import DatabaseSettings as DatabaseSettings
    from arvel.data.exceptions import (
        ConfigurationError as ConfigurationError,
        CreationAbortedError as CreationAbortedError,
        DataError as DataError,
        DeletionAbortedError as DeletionAbortedError,
        IntegrityError as IntegrityError,
        MassAssignmentError as MassAssignmentError,
        NotFoundError as NotFoundError,
        TransactionError as TransactionError,
        UpdateAbortedError as UpdateAbortedError,
    )
    from arvel.data.materialized_view import (
        MaterializedView as MaterializedView,
        ViewRegistry as ViewRegistry,
        detect_pg_ivm as detect_pg_ivm,
    )
    from arvel.data.migrations import MigrationRunner as MigrationRunner
    from arvel.data.migrations import MigrationStatusEntry as MigrationStatusEntry
    from arvel.data.migrations import register_framework_migration as register_framework_migration
    from arvel.data.migrations import run_alembic_env as run_alembic_env
    from arvel.data.model import ArvelModel as ArvelModel
    from arvel.data.observer import ModelObserver as ModelObserver
    from arvel.data.observer import ObserverRegistry as ObserverRegistry
    from arvel.data.pagination import CursorMeta as CursorMeta
    from arvel.data.pagination import CursorResponse as CursorResponse
    from arvel.data.pagination import CursorResult as CursorResult
    from arvel.data.pagination import PaginatedResponse as PaginatedResponse
    from arvel.data.pagination import PaginatedResult as PaginatedResult
    from arvel.data.pagination import PaginationMeta as PaginationMeta
    from arvel.data.provider import DatabaseServiceProvider as DatabaseServiceProvider
    from arvel.data.query import QueryBuilder as QueryBuilder
    from arvel.data.query import RecursiveQueryBuilder as RecursiveQueryBuilder
    from arvel.data.relationships import (
        ComparisonOperator as ComparisonOperator,
        HasRelationships as HasRelationships,
        LazyLoadError as LazyLoadError,
        PivotManager as PivotManager,
        RelationshipDescriptor as RelationshipDescriptor,
        RelationType as RelationType,
        belongs_to as belongs_to,
        belongs_to_many as belongs_to_many,
        has_many as has_many,
        has_one as has_one,
    )
    from arvel.data.relationships.morphs import (
        load_morph_parent as load_morph_parent,
        morph_many as morph_many,
        morph_to as morph_to,
        morph_to_many as morph_to_many,
        query_morph_children as query_morph_children,
        register_morph_type as register_morph_type,
    )
    from arvel.data.repository import Repository as Repository
    from arvel.data.results import TreeNode as TreeNode
    from arvel.data.results import WithCount as WithCount
    from arvel.data.scopes import GlobalScope as GlobalScope
    from arvel.data.scopes import scope as scope
    from arvel.data.seeder import Seeder as Seeder
    from arvel.data.seeder import SeedRunner as SeedRunner
    from arvel.data.seeder import discover_seeders as discover_seeders
    from arvel.data.schema import Blueprint as Blueprint
    from arvel.data.schema import ColumnBuilder as ColumnBuilder
    from arvel.data.schema import ForeignKeyAction as ForeignKeyAction
    from arvel.data.schema import KeyType as KeyType
    from arvel.data.schema import Schema as Schema
    from arvel.data.soft_deletes import SoftDeletes as SoftDeletes
    from arvel.data.transaction import Transaction as Transaction

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    # accessors
    "accessor": ("arvel.data.accessors", "accessor"),
    "mutator": ("arvel.data.accessors", "mutator"),
    # casts
    "Caster": ("arvel.data.casts", "Caster"),
    "EncryptedCaster": ("arvel.data.casts", "EncryptedCaster"),
    "EnumCaster": ("arvel.data.casts", "EnumCaster"),
    "JsonCaster": ("arvel.data.casts", "JsonCaster"),
    # collection
    "ArvelCollection": ("arvel.data.collection", "ArvelCollection"),
    "collect": ("arvel.data.collection", "collect"),
    # config
    "DatabaseSettings": ("arvel.data.config", "DatabaseSettings"),
    # exceptions
    "ConfigurationError": ("arvel.data.exceptions", "ConfigurationError"),
    "CreationAbortedError": ("arvel.data.exceptions", "CreationAbortedError"),
    "DataError": ("arvel.data.exceptions", "DataError"),
    "DeletionAbortedError": ("arvel.data.exceptions", "DeletionAbortedError"),
    "IntegrityError": ("arvel.data.exceptions", "IntegrityError"),
    "MassAssignmentError": ("arvel.data.exceptions", "MassAssignmentError"),
    "NotFoundError": ("arvel.data.exceptions", "NotFoundError"),
    "TransactionError": ("arvel.data.exceptions", "TransactionError"),
    "UpdateAbortedError": ("arvel.data.exceptions", "UpdateAbortedError"),
    # materialized_view
    "MaterializedView": ("arvel.data.materialized_view", "MaterializedView"),
    "ViewRegistry": ("arvel.data.materialized_view", "ViewRegistry"),
    "detect_pg_ivm": ("arvel.data.materialized_view", "detect_pg_ivm"),
    # migrations
    "MigrationRunner": ("arvel.data.migrations", "MigrationRunner"),
    "MigrationStatusEntry": ("arvel.data.migrations", "MigrationStatusEntry"),
    "register_framework_migration": ("arvel.data.migrations", "register_framework_migration"),
    "run_alembic_env": ("arvel.data.migrations", "run_alembic_env"),
    # model
    "ArvelModel": ("arvel.data.model", "ArvelModel"),
    # observer
    "ModelObserver": ("arvel.data.observer", "ModelObserver"),
    "ObserverRegistry": ("arvel.data.observer", "ObserverRegistry"),
    # pagination
    "CursorMeta": ("arvel.data.pagination", "CursorMeta"),
    "CursorResponse": ("arvel.data.pagination", "CursorResponse"),
    "CursorResult": ("arvel.data.pagination", "CursorResult"),
    "PaginatedResponse": ("arvel.data.pagination", "PaginatedResponse"),
    "PaginatedResult": ("arvel.data.pagination", "PaginatedResult"),
    "PaginationMeta": ("arvel.data.pagination", "PaginationMeta"),
    # provider
    "DatabaseServiceProvider": ("arvel.data.provider", "DatabaseServiceProvider"),
    # query
    "QueryBuilder": ("arvel.data.query", "QueryBuilder"),
    "RecursiveQueryBuilder": ("arvel.data.query", "RecursiveQueryBuilder"),
    # relationships
    "ComparisonOperator": ("arvel.data.relationships", "ComparisonOperator"),
    "HasRelationships": ("arvel.data.relationships", "HasRelationships"),
    "LazyLoadError": ("arvel.data.relationships", "LazyLoadError"),
    "PivotManager": ("arvel.data.relationships", "PivotManager"),
    "RelationshipDescriptor": ("arvel.data.relationships", "RelationshipDescriptor"),
    "RelationType": ("arvel.data.relationships", "RelationType"),
    "belongs_to": ("arvel.data.relationships", "belongs_to"),
    "belongs_to_many": ("arvel.data.relationships", "belongs_to_many"),
    "has_many": ("arvel.data.relationships", "has_many"),
    "has_one": ("arvel.data.relationships", "has_one"),
    # relationships.morphs
    "load_morph_parent": ("arvel.data.relationships.morphs", "load_morph_parent"),
    "morph_many": ("arvel.data.relationships.morphs", "morph_many"),
    "morph_to": ("arvel.data.relationships.morphs", "morph_to"),
    "morph_to_many": ("arvel.data.relationships.morphs", "morph_to_many"),
    "query_morph_children": ("arvel.data.relationships.morphs", "query_morph_children"),
    "register_morph_type": ("arvel.data.relationships.morphs", "register_morph_type"),
    # repository
    "Repository": ("arvel.data.repository", "Repository"),
    # results
    "TreeNode": ("arvel.data.results", "TreeNode"),
    "WithCount": ("arvel.data.results", "WithCount"),
    # scopes
    "GlobalScope": ("arvel.data.scopes", "GlobalScope"),
    "scope": ("arvel.data.scopes", "scope"),
    # seeder
    "Seeder": ("arvel.data.seeder", "Seeder"),
    "SeedRunner": ("arvel.data.seeder", "SeedRunner"),
    "discover_seeders": ("arvel.data.seeder", "discover_seeders"),
    # schema
    "Blueprint": ("arvel.data.schema", "Blueprint"),
    "ColumnBuilder": ("arvel.data.schema", "ColumnBuilder"),
    "ForeignKeyAction": ("arvel.data.schema", "ForeignKeyAction"),
    "KeyType": ("arvel.data.schema", "KeyType"),
    "Schema": ("arvel.data.schema", "Schema"),
    # soft_deletes
    "SoftDeletes": ("arvel.data.soft_deletes", "SoftDeletes"),
    # transaction
    "Transaction": ("arvel.data.transaction", "Transaction"),
    # alembic
    "op": ("alembic", "op"),
    # sqlalchemy types
    "BigInteger": ("sqlalchemy", "BigInteger"),
    "Boolean": ("sqlalchemy", "Boolean"),
    "Column": ("sqlalchemy", "Column"),
    "DateTime": ("sqlalchemy", "DateTime"),
    "Float": ("sqlalchemy", "Float"),
    "Integer": ("sqlalchemy", "Integer"),
    "Numeric": ("sqlalchemy", "Numeric"),
    "String": ("sqlalchemy", "String"),
    "Text": ("sqlalchemy", "Text"),
    "Uuid": ("sqlalchemy", "Uuid"),
    # sqlalchemy.orm
    "Mapped": ("sqlalchemy.orm", "Mapped"),
    "mapped_column": ("sqlalchemy.orm", "mapped_column"),
}


def __getattr__(name: str) -> object:
    entry = _LAZY_IMPORTS.get(name)
    if entry is not None:
        module_path, attr_name = entry
        import importlib

        module = importlib.import_module(module_path)
        value = getattr(module, attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ArvelCollection",
    "ArvelModel",
    "BigInteger",
    "Blueprint",
    "Boolean",
    "Caster",
    "Column",
    "ColumnBuilder",
    "ComparisonOperator",
    "ConfigurationError",
    "CreationAbortedError",
    "CursorMeta",
    "CursorResponse",
    "CursorResult",
    "DataError",
    "DatabaseServiceProvider",
    "DatabaseSettings",
    "DateTime",
    "DeletionAbortedError",
    "EncryptedCaster",
    "EnumCaster",
    "Float",
    "ForeignKeyAction",
    "GlobalScope",
    "HasRelationships",
    "Integer",
    "IntegrityError",
    "JsonCaster",
    "KeyType",
    "LazyLoadError",
    "Mapped",
    "MassAssignmentError",
    "MaterializedView",
    "MigrationRunner",
    "MigrationStatusEntry",
    "ModelObserver",
    "NotFoundError",
    "Numeric",
    "ObserverRegistry",
    "PaginatedResponse",
    "PaginatedResult",
    "PaginationMeta",
    "PivotManager",
    "QueryBuilder",
    "RecursiveQueryBuilder",
    "RelationType",
    "RelationshipDescriptor",
    "Repository",
    "Schema",
    "SeedRunner",
    "Seeder",
    "SoftDeletes",
    "String",
    "Text",
    "Transaction",
    "TransactionError",
    "TreeNode",
    "UpdateAbortedError",
    "Uuid",
    "ViewRegistry",
    "WithCount",
    "accessor",
    "belongs_to",
    "belongs_to_many",
    "collect",
    "detect_pg_ivm",
    "discover_seeders",
    "has_many",
    "has_one",
    "load_morph_parent",
    "mapped_column",
    "morph_many",
    "morph_to",
    "morph_to_many",
    "mutator",
    "op",
    "query_morph_children",
    "register_framework_migration",
    "register_morph_type",
    "run_alembic_env",
    "scope",
]
