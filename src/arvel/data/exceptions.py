"""Data layer exception hierarchy.

All data exceptions carry structured context (model name, record ID)
without exposing raw SQL or connection strings.
"""

from __future__ import annotations

from arvel.foundation.exceptions import ArvelError


class DataError(ArvelError):
    """Base for all data layer exceptions."""


class NotFoundError(DataError):
    """Raised when a record is not found by ID.

    Attributes:
        model_name: The model class name.
        record_id: The ID that was searched for.
    """

    def __init__(
        self,
        message: str,
        *,
        model_name: str,
        record_id: int | str,
    ) -> None:
        super().__init__(message)
        self.model_name = model_name
        self.record_id = record_id


class CreationAbortedError(DataError):
    """Raised when an observer vetoes record creation.

    Attributes:
        model_name: The model class name.
        observer_name: The observer that vetoed.
    """

    def __init__(
        self,
        message: str,
        *,
        model_name: str,
        observer_name: str = "",
    ) -> None:
        super().__init__(message)
        self.model_name = model_name
        self.observer_name = observer_name


class UpdateAbortedError(DataError):
    """Raised when an observer vetoes a record update.

    Attributes:
        model_name: The model class name.
        observer_name: The observer that vetoed.
    """

    def __init__(
        self,
        message: str,
        *,
        model_name: str,
        observer_name: str = "",
    ) -> None:
        super().__init__(message)
        self.model_name = model_name
        self.observer_name = observer_name


class DeletionAbortedError(DataError):
    """Raised when an observer vetoes a record deletion.

    Attributes:
        model_name: The model class name.
        observer_name: The observer that vetoed.
    """

    def __init__(
        self,
        message: str,
        *,
        model_name: str,
        observer_name: str = "",
    ) -> None:
        super().__init__(message)
        self.model_name = model_name
        self.observer_name = observer_name


class ConfigurationError(DataError):
    """Raised when a model or repository is misconfigured.

    Examples: setting both ``__fillable__`` and ``__guarded__``,
    missing required config, or conflicting options.
    """


class MassAssignmentError(DataError):
    """Raised in strict mode when a guarded field is assigned.

    Attributes:
        model_name: The model class name.
        field_name: The field that was blocked.
    """

    def __init__(
        self,
        message: str,
        *,
        model_name: str,
        field_name: str,
    ) -> None:
        super().__init__(message)
        self.model_name = model_name
        self.field_name = field_name


class IntegrityError(DataError):
    """Raised when a database constraint is violated.

    Wraps SA's IntegrityError with a human-readable message.
    """


class TransactionError(DataError):
    """Raised when a database transaction fails."""
