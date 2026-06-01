"""Database query tracing and metrics."""

from __future__ import annotations

import pytest


class TestDbTracingConfig:
    def test_db_slow_query_ms_default(self) -> None:
        from arvel.observability.config import ObservabilityConfig

        config = ObservabilityConfig()
        assert config.db_slow_query_ms == 200

    def test_db_query_log_enabled_default(self) -> None:
        from arvel.observability.config import ObservabilityConfig

        config = ObservabilityConfig()
        assert config.db_query_log_enabled is True

    def test_db_query_log_can_be_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DB_QUERY_LOG_ENABLED", "false")
        from arvel.observability.config import ObservabilityConfig

        config = ObservabilityConfig()
        assert config.db_query_log_enabled is False


class TestQueryLoggingProviderDeleted:
    def test_query_logging_service_provider_no_longer_exists(self) -> None:
        """QueryLoggingServiceProvider must be removed after ."""
        import importlib

        try:
            mod = importlib.import_module("arvel.database.query_logging")
            assert not hasattr(mod, "QueryLoggingServiceProvider"), (
                "QueryLoggingServiceProvider must be removed from query_logging.py"
            )
        except ImportError:
            pass  # module removed entirely is also fine

    def test_query_log_capture_helper_still_exists(self) -> None:
        """QueryLog.capture() is a test utility and must survive the refactor."""
        from arvel.database.query_logging import QueryLog

        assert hasattr(QueryLog, "capture")


class TestSlowQueryLog:
    @pytest.mark.asyncio
    async def test_slow_query_emits_warning_log(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A query above the threshold must emit a WARNING Log record."""
        from arvel.observability.slow_query import check_and_log_slow_query
        from arvel.testing.observability import FakeObservability

        monkeypatch.setenv("DB_SLOW_QUERY_MS", "100")

        with FakeObservability() as obs:
            # Simulate a 250ms query
            await check_and_log_slow_query(
                sql="SELECT * FROM users",
                duration_ms=250.0,
                threshold_ms=100,
            )

        obs.assert_logged("db.slow_query")
        slow_rec = next(r for r in obs.log_records if r.body == "db.slow_query")
        assert slow_rec.attributes.get("duration_ms") is not None
        assert slow_rec.attributes.get("threshold_ms") == 100

    @pytest.mark.asyncio
    async def test_fast_query_does_not_emit_slow_log(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from arvel.observability.slow_query import check_and_log_slow_query
        from arvel.testing.observability import FakeObservability

        monkeypatch.setenv("DB_SLOW_QUERY_MS", "100")

        with FakeObservability() as obs:
            await check_and_log_slow_query(
                sql="SELECT 1",
                duration_ms=50.0,
                threshold_ms=100,
            )

        slow_recs = [r for r in obs.log_records if r.body == "db.slow_query"]
        assert not slow_recs
