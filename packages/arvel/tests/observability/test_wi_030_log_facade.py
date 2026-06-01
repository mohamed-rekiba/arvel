"""Log facade → OTel Logs."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from arvel.testing.observability import FakeObservability


@pytest.fixture
def obs() -> FakeObservability:
    """FakeObservability context (helper — tested separately)."""
    from arvel.testing.observability import FakeObservability

    return FakeObservability()


class TestLogFacadeImport:
    def test_facades_import_works(self) -> None:
        from arvel.facades import Log

        _ = Log

    def test_logging_import_still_works(self) -> None:
        from arvel.logging import Log

        _ = Log

    def test_both_are_same_object(self) -> None:
        from arvel.facades import Log as FacadesLog
        from arvel.logging import Log as LoggingLog

        assert FacadesLog is LoggingLog


class TestLogFacadeApi:
    def test_info_accepts_event_and_kwargs(self) -> None:
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            Log.info("test.event", field1="val1", field2=42)
        obs.assert_logged("test.event", field1="val1", field2=42)

    def test_warning_emits_log_record(self) -> None:
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            Log.warning("test.warning", code=42)
        obs.assert_logged("test.warning", code=42)

    def test_error_emits_log_record(self) -> None:
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            Log.error("test.error")
        obs.assert_logged("test.error")

    def test_critical_emits_log_record(self) -> None:
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            Log.critical("test.critical")
        obs.assert_logged("test.critical")

    def test_debug_emits_log_record(self) -> None:
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            Log.debug("test.debug")
        obs.assert_logged("test.debug")

    def test_with_context_returns_child_logger(self) -> None:
        from arvel.facades import Log
        from arvel.logging.otel_logger import OtelLogger

        child = Log.with_context(user_id=99)
        assert isinstance(child, OtelLogger)

    def test_with_context_binds_fields_to_all_records(self) -> None:
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            child = Log.with_context(tenant="acme")
            child.info("something.happened")
            child.info("something.else")
        # Both records carry tenant
        records = [r for r in obs.log_records if r.body in {"something.happened", "something.else"}]
        assert all(r.attributes.get("tenant") == "acme" for r in records)

    def test_with_context_does_not_affect_parent(self) -> None:
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            child = Log.with_context(tenant="acme")
            child.info("child.event")
            Log.info("parent.event")

        child_rec = next(r for r in obs.log_records if r.body == "child.event")
        parent_rec = next(r for r in obs.log_records if r.body == "parent.event")

        assert child_rec.attributes.get("tenant") == "acme"
        assert "tenant" not in parent_rec.attributes

    def test_channel_returns_scoped_logger(self) -> None:
        from arvel.facades import Log
        from arvel.logging.otel_logger import OtelLogger

        audit = Log.channel("audit")
        assert isinstance(audit, OtelLogger)

    def test_channel_logger_name_prefix(self) -> None:
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            Log.channel("audit").info("user.deleted", user_id=42)

        record = next(r for r in obs.log_records if r.body == "user.deleted")
        # OTel logger name should be "arvel.audit"
        assert record.instrumentation_scope.name == "arvel.audit"

    def test_error_with_exc_info_attaches_exception_attrs(self) -> None:
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            try:
                raise ValueError("boom")
            except ValueError:
                Log.error("caught.error", exc_info=True)

        record = next(r for r in obs.log_records if r.body == "caught.error")
        assert record.attributes.get("exception.type") is not None
        assert record.attributes.get("exception.message") is not None


class TestLogRedaction:
    def test_password_field_is_redacted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOG_REDACT_FIELDS", "password,token")
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            Log.info("auth.attempt", username="alice", password="secret123")

        record = next(r for r in obs.log_records if r.body == "auth.attempt")
        assert record.attributes.get("password") == "[REDACTED]"
        assert record.attributes.get("username") == "alice"

    def test_default_redact_fields_cover_known_secrets(self) -> None:
        from arvel.observability.config import ObservabilityConfig

        config = ObservabilityConfig()
        assert "password" in config.log_redact_fields
        assert "token" in config.log_redact_fields
        assert "secret" in config.log_redact_fields
        assert "authorization" in config.log_redact_fields


class TestLogLevelGating:
    def test_debug_suppressed_at_info_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOG_LEVEL", "info")
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            Log.debug("debug.event")

        debug_records = [r for r in obs.log_records if r.body == "debug.event"]
        assert len(debug_records) == 0

    def test_info_passes_at_info_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOG_LEVEL", "info")
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            Log.info("info.event")

        obs.assert_logged("info.event")


class TestNoStructlogInFrameworkInternals:
    def test_facades_module_does_not_import_structlog_get_logger(self) -> None:
        """Verify the facades module itself does not call structlog.get_logger."""
        import ast
        import importlib.util
        from pathlib import Path

        spec = importlib.util.find_spec("arvel.facades")
        assert spec is not None
        src = Path(spec.origin or "").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and (
                node.attr == "get_logger"
                and isinstance(node.value, ast.Name)
                and node.value.id == "structlog"
            ):
                pytest.fail("arvel.facades uses structlog.get_logger()")
