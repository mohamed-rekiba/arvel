"""Tests for Foundation exception hierarchy.

Ensures all exception types are importable, carry correct attributes,
and form the expected inheritance chain.
"""

from __future__ import annotations

import pytest

from arvel.foundation.exceptions import (
    ArvelError,
    BootError,
    ConfigurationError,
    DependencyError,
    ProviderNotFoundError,
)


class TestExceptionHierarchy:
    """All Foundation exceptions inherit from ArvelError."""

    @pytest.mark.parametrize(
        "exc_class",
        [
            ConfigurationError,
            ProviderNotFoundError,
            BootError,
            DependencyError,
        ],
    )
    def test_inherits_from_arvel_error(self, exc_class: type) -> None:
        assert issubclass(exc_class, ArvelError)


class TestConfigurationError:
    """ConfigurationError carries field and env_var context."""

    def test_field_attribute(self) -> None:
        err = ConfigurationError("bad value", field="db_host", env_var="DB_HOST")
        assert err.field == "db_host"
        assert err.env_var == "DB_HOST"

    def test_message(self) -> None:
        err = ConfigurationError("Missing required env var: DB_HOST")
        assert "DB_HOST" in str(err)


class TestProviderNotFoundError:
    """ProviderNotFoundError carries module_path."""

    def test_module_path_attribute(self) -> None:
        err = ProviderNotFoundError(
            "No ServiceProvider in module", module_path="/app/modules/broken"
        )
        assert err.module_path == "/app/modules/broken"


class TestBootError:
    """BootError carries provider_name and cause."""

    def test_attributes(self) -> None:
        cause = RuntimeError("oops")
        err = BootError("Boot failed", provider_name="UsersProvider", cause=cause)
        assert err.provider_name == "UsersProvider"
        assert err.cause is cause


class TestDependencyError:
    """DependencyError carries requested_type."""

    def test_requested_type_attribute(self) -> None:
        err = DependencyError("Not found", requested_type=str)
        assert err.requested_type is str
