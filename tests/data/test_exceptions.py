"""Tests for the data layer exception hierarchy.

Covers: SAD-003 D8 — typed exceptions with context.
"""

from __future__ import annotations

from arvel.data.exceptions import (
    CreationAbortedError,
    DataError,
    DeletionAbortedError,
    IntegrityError,
    NotFoundError,
    TransactionError,
    UpdateAbortedError,
)
from arvel.foundation.exceptions import ArvelError


class TestExceptionHierarchy:
    """All data exceptions extend DataError which extends ArvelError."""

    def test_data_error_is_arvel_error(self) -> None:
        assert issubclass(DataError, ArvelError)

    def test_not_found_error_is_data_error(self) -> None:
        assert issubclass(NotFoundError, DataError)

    def test_creation_aborted_error_is_data_error(self) -> None:
        assert issubclass(CreationAbortedError, DataError)

    def test_update_aborted_error_is_data_error(self) -> None:
        assert issubclass(UpdateAbortedError, DataError)

    def test_deletion_aborted_error_is_data_error(self) -> None:
        assert issubclass(DeletionAbortedError, DataError)

    def test_integrity_error_is_data_error(self) -> None:
        assert issubclass(IntegrityError, DataError)

    def test_transaction_error_is_data_error(self) -> None:
        assert issubclass(TransactionError, DataError)


class TestNotFoundErrorContext:
    """NotFoundError carries model name and record ID."""

    def test_not_found_error_attributes(self) -> None:
        err = NotFoundError("User not found", model_name="User", record_id=42)
        assert err.model_name == "User"
        assert err.record_id == 42
        assert "User not found" in str(err)


class TestCreationAbortedErrorContext:
    """CreationAbortedError carries model name and observer info."""

    def test_creation_aborted_attributes(self) -> None:
        err = CreationAbortedError(
            "Creation aborted by observer", model_name="User", observer_name="AuditObserver"
        )
        assert err.model_name == "User"
        assert err.observer_name == "AuditObserver"


class TestUpdateAbortedErrorContext:
    """UpdateAbortedError carries model name and observer info."""

    def test_update_aborted_attributes(self) -> None:
        err = UpdateAbortedError(
            "Update aborted by observer", model_name="Order", observer_name="LockObserver"
        )
        assert err.model_name == "Order"
        assert err.observer_name == "LockObserver"


class TestDeletionAbortedErrorContext:
    """DeletionAbortedError carries model name and observer info."""

    def test_deletion_aborted_attributes(self) -> None:
        err = DeletionAbortedError(
            "Deletion aborted by observer", model_name="Invoice", observer_name="ProtectObserver"
        )
        assert err.model_name == "Invoice"
        assert err.observer_name == "ProtectObserver"
