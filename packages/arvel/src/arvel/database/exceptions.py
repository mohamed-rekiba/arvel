"""Typed exceptions raised by the ORM."""

from __future__ import annotations


class ORMError(Exception):
    """Base class for all ORM-raised errors."""


class ModelNotFoundError(ORMError):
    """Raised by ``find_or_fail`` / ``first_or_fail`` when no row matches.

    The message includes the model class name and the lookup key.
    """

    def __init__(self, model_name: str, key: object) -> None:
        super().__init__(f"No {model_name} found for key={key!r}.")
        self.model_name = model_name
        self.key = key


class RelationNotLoadedError(ORMError):
    """Raised by ``to_pydantic`` when a referenced relation isn't eager-loaded."""

    def __init__(self, model_name: str, relation: str) -> None:
        super().__init__(
            f"{model_name}.{relation} was not loaded; eager-load it with "
            f".with_({relation!r}) before calling to_pydantic()."
        )
        self.model_name = model_name
        self.relation = relation


class UnknownRelationError(ORMError):
    """Raised by ``QueryBuilder.with_`` when a relation name isn't defined on the model."""

    def __init__(self, model_name: str, relation: str) -> None:
        super().__init__(
            f"{model_name} has no relation named {relation!r}. "
            f"Check the spelling or define it via SQLA relationship()."
        )
        self.model_name = model_name
        self.relation = relation


class DecryptionError(ORMError):
    """Raised by ``EncryptedType`` when ciphertext can't be decrypted (wrong key / tampered)."""


class MigrationNotReversibleError(ORMError):
    """Raised when a Migration with ``Schema.drop_*`` / ``drop_column`` lacks a ``down()`` body."""

    def __init__(self, migration_class: str, op: str) -> None:
        super().__init__(
            f"Migration {migration_class} uses {op} in up() but down() is empty. "
            "Implement down() to make the migration reversible."
        )
        self.migration_class = migration_class
        self.op = op


class DatabaseConnectionError(ORMError):
    """Raised by ``DatabaseServiceProvider.boot()`` when the engine can't reach the DB.

    The original URL is redacted in the message — only the driver and host
    appear in the public string.
    """

    def __init__(self, driver: str, host: str, inner: BaseException) -> None:
        super().__init__(
            f"Database connection failed (driver={driver}, host={host}): {type(inner).__name__}"
        )
        self.driver = driver
        self.host = host
        self.__cause__ = inner


class QueryCompileError(ORMError):
    """Raised when QueryBuilder.to_sql() cannot compile the query with literal binds."""


class MassAssignmentError(ORMError):
    """Raised when create()/update() receives a field blocked by __fillable__ or __guarded__."""

    def __init__(self, model_name: str, field: str) -> None:
        super().__init__(
            f"Field '{field}' is not mass-assignable on {model_name}. "
            "Add it to __fillable__ or remove it from __guarded__."
        )
        self.model_name = model_name
        self.field = field


class MultipleResultsError(ORMError):
    """Raised by QueryBuilder.sole() when more than one row matches."""

    def __init__(self, model_name: str) -> None:
        super().__init__(f"Expected exactly one {model_name} but found multiple rows.")
        self.model_name = model_name


class CastError(ORMError):
    """Raised when a value can't be coerced to the type its ``__casts__`` entry asks for."""

    def __init__(self, cast_type: str, value: object, reason: str | None = None) -> None:
        detail = f": {reason}" if reason else ""
        super().__init__(
            f"Cannot cast {value!r} (type {type(value).__name__}) to {cast_type}{detail}."
        )
        self.cast_type = cast_type
        self.value = value


class OperationCancelledError(ORMError):
    """Raised when a ``creating`` / ``updating`` / ``deleting`` hook returns ``False``."""

    def __init__(self, model_name: str, event_name: str) -> None:
        super().__init__(f"{model_name} {event_name} hook returned False — operation aborted.")
        self.model_name = model_name
        self.event_name = event_name


class ReadOnlyModelError(ORMError):
    """Raised when a write operation is attempted on a ViewModel.

    ViewModels are read-only by design — use Schema DDL methods to manage
    the underlying view, and Schema.refresh_materialized_view() (or
    ViewModel.refresh()) for materialized views.
    """

    def __init__(self, model_name: str, operation: str) -> None:
        super().__init__(
            f"{model_name} is a read-only view model — {operation}() is not allowed. "
            "Use Schema DDL methods to manage views."
        )
        self.model_name = model_name
        self.operation = operation


class OutsideTransactionError(ORMError):
    """Raised by DomainService.get_for_write() when called outside a DB.transaction() block."""

    def __init__(self) -> None:
        super().__init__(
            "DomainService.get_for_write() must be called inside a DB.transaction() block. "
            "The read/write split pattern is only safe within a transaction boundary."
        )


class ReadModelNotFoundError(ORMError):
    """Raised by DomainService.get_for_write() when the read-model row does not exist.

    Raised before the write-side lock is attempted to avoid unnecessary contention.
    """

    def __init__(self, read_model_name: str, key: object) -> None:
        super().__init__(
            f"No {read_model_name} found for key={key!r}. "
            "The resource may be unpublished or unavailable; write-side lock was not acquired."
        )
        self.read_model_name = read_model_name
        self.key = key


__all__ = [
    "CastError",
    "DatabaseConnectionError",
    "DecryptionError",
    "MassAssignmentError",
    "MigrationNotReversibleError",
    "ModelNotFoundError",
    "MultipleResultsError",
    "ORMError",
    "OperationCancelledError",
    "OutsideTransactionError",
    "QueryCompileError",
    "ReadModelNotFoundError",
    "ReadOnlyModelError",
    "RelationNotLoadedError",
    "UnknownRelationError",
]
