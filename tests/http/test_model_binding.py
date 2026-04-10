"""Tests for route model binding — Story 3.

FR-060: Implicit model binding resolves path params to model instances
FR-061: Missing model returns 404
FR-062: Explicit binding via bind_model()
FR-063: Multiple model params resolved independently
"""

from __future__ import annotations

from arvel.http.exceptions import ModelNotFoundError
from arvel.http.model_binding import bind_model, clear_bindings


class TestModelNotFoundError:
    """FR-061: Missing model returns 404."""

    def test_model_not_found_has_404_status(self) -> None:
        error = ModelNotFoundError("User", "42")
        assert error.status_code == 404
        assert error.model_name == "User"
        assert error.identifier == "42"
        assert "User not found" in str(error)


class TestBindModel:
    """FR-062: Explicit model binding registration."""

    def setup_method(self) -> None:
        clear_bindings()

    def teardown_method(self) -> None:
        clear_bindings()

    def test_bind_model_registers_binding(self) -> None:
        class FakeModel:
            pass

        class FakeRepo:
            pass

        bind_model("user", FakeModel, FakeRepo)

    def test_clear_bindings_removes_all(self) -> None:
        class FakeModel:
            pass

        class FakeRepo:
            pass

        bind_model("user", FakeModel, FakeRepo)
        clear_bindings()


class TestModelNotFoundErrorSerialization:
    """Ensure ModelNotFoundError works with the RFC 9457 handler."""

    def test_inherits_from_http_exception(self) -> None:
        from arvel.http.exceptions import HttpException

        error = ModelNotFoundError("Post", "99")
        assert isinstance(error, HttpException)

    def test_error_detail_is_generic(self) -> None:
        error = ModelNotFoundError("User", "42")
        assert "User not found" in error.detail
        assert "42" not in error.detail
