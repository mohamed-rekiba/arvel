"""FR-003-043 — typed exception messages and inheritance."""

from __future__ import annotations

from arvel.database import (
    DatabaseConnectionError,
    DecryptionError,
    MigrationNotReversibleError,
    ModelNotFoundError,
    RelationNotLoadedError,
    UnknownRelationError,
)
from arvel.database.exceptions import ORMError


def test_all_inherit_from_orm_error() -> None:
    assert issubclass(ModelNotFoundError, ORMError)
    assert issubclass(RelationNotLoadedError, ORMError)
    assert issubclass(UnknownRelationError, ORMError)
    assert issubclass(DecryptionError, ORMError)
    assert issubclass(MigrationNotReversibleError, ORMError)
    assert issubclass(DatabaseConnectionError, ORMError)


def test_model_not_found_includes_key_in_message() -> None:
    err = ModelNotFoundError("User", 42)
    assert "User" in str(err)
    assert "42" in str(err)


def test_database_connection_error_redacts_credentials() -> None:
    cause = RuntimeError("boom")
    err = DatabaseConnectionError(driver="postgresql", host="db.internal", inner=cause)
    msg = str(err)
    assert "postgresql" in msg
    assert "db.internal" in msg
    # The inner exception's repr is summarised, not pasted whole.
    assert "boom" not in msg
