"""arvel.database — Active-Record ORM over SQLAlchemy Core (DR-0002).

Built on the **SQLAlchemy Core expression language** (not the ORM Session),
lazy-imported behind the connection so ``import arvel`` stays light. Grows across
Phase 5: connections · query builder · Model · relations · migrations.
Grounded in knowledge/port/07-orm-active-record.md.
"""

from __future__ import annotations

from typing import Any

from arvel.database.attribute import Attribute
from arvel.database.builder import Builder
from arvel.database.connections import ConnectionResolver, QueryExecuted, WriteResult
from arvel.database.factory import Factory, FactoryBatch
from arvel.database.migrations import Migration, Migrator, Schema, discover_migrations
from arvel.database.model import (
    HasUlids,
    HasUuids,
    MassAssignmentException,
    Model,
    Prunable,
    ReadOnlyModelError,
    SoftDeletes,
    scope,
)
from arvel.database.schema import Blueprint
from arvel.database.seeder import Seeder


def raw(sql: str) -> Any:
    """A raw SQL fragment as a SQLAlchemy Core ``text()`` construct."""
    import sqlalchemy as sa

    return sa.text(sql)


__all__ = [
    "Attribute",
    "Blueprint",
    "Builder",
    "ConnectionResolver",
    "Factory",
    "FactoryBatch",
    "HasUlids",
    "HasUuids",
    "MassAssignmentException",
    "Migration",
    "Migrator",
    "Model",
    "Prunable",
    "QueryExecuted",
    "ReadOnlyModelError",
    "Schema",
    "Seeder",
    "SoftDeletes",
    "WriteResult",
    "discover_migrations",
    "raw",
    "scope",
]
