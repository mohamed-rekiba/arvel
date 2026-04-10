"""Tests for observability exception types."""

from __future__ import annotations

from arvel.observability.exceptions import HealthCheckTimeoutError, TracingConfigError


class TestHealthCheckTimeoutError:
    def test_stores_check_name(self) -> None:
        err = HealthCheckTimeoutError(check_name="db", timeout=5.0)
        assert err.check_name == "db"

    def test_stores_timeout(self) -> None:
        err = HealthCheckTimeoutError(check_name="redis", timeout=3.0)
        assert err.timeout == 3.0

    def test_message_includes_name_and_timeout(self) -> None:
        err = HealthCheckTimeoutError(check_name="db", timeout=5.0)
        msg = str(err)
        assert "db" in msg
        assert "5.0" in msg

    def test_is_exception(self) -> None:
        err = HealthCheckTimeoutError(check_name="db", timeout=1.0)
        assert isinstance(err, Exception)


class TestTracingConfigError:
    def test_message_propagation(self) -> None:
        err = TracingConfigError("Missing OTEL endpoint")
        assert str(err) == "Missing OTEL endpoint"

    def test_is_exception(self) -> None:
        err = TracingConfigError("bad config")
        assert isinstance(err, Exception)
