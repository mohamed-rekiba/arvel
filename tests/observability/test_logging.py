"""Tests for structured logging — FR-001 to FR-012, SEC-001, SEC-002."""

from __future__ import annotations

import json
import logging
from logging.handlers import TimedRotatingFileHandler

import structlog

from arvel.logging import bind_log_context, clear_log_context
from arvel.observability.config import ObservabilitySettings
from arvel.observability.logging import (
    RedactProcessor,
    RequestIdProcessor,
    configure_logging,
)


class TestConfigureLogging:
    def test_configure_logging_returns_none(self) -> None:
        """FR-001: configure_logging configures structlog globally."""
        settings = ObservabilitySettings(log_format="console")
        result = configure_logging(settings, app_env="development", app_debug=False)
        assert result is None

    def test_json_renderer_in_production(self) -> None:
        """FR-002: JSON renderer when log_format=json."""
        settings = ObservabilitySettings(log_format="json")
        configure_logging(settings, app_env="production", app_debug=False)
        logger = structlog.get_logger()
        assert logger is not None

    def test_console_renderer_in_development(self) -> None:
        """FR-003: Console renderer when log_format=console."""
        settings = ObservabilitySettings(log_format="console")
        configure_logging(settings, app_env="development", app_debug=False)
        logger = structlog.get_logger()
        assert logger is not None

    def test_auto_format_production_uses_json(self) -> None:
        """FR-011: auto format resolves to json in production."""
        settings = ObservabilitySettings(log_format="auto")
        configure_logging(settings, app_env="production", app_debug=False)
        config = structlog.get_config()
        processors = config.get("processors", [])
        assert len(processors) > 0

    def test_auto_format_development_uses_console(self) -> None:
        """FR-011: auto format resolves to console in development."""
        settings = ObservabilitySettings(log_format="auto")
        configure_logging(settings, app_env="development", app_debug=False)
        config = structlog.get_config()
        assert len(config.get("processors", [])) > 0

    def test_stdlib_bridge_configured(self) -> None:
        """FR-012: stdlib logging bridged to structlog."""
        import logging

        settings = ObservabilitySettings(log_format="console")
        configure_logging(settings, app_env="development", app_debug=False)
        root = logging.getLogger()
        assert len(root.handlers) > 0

    def test_console_renderer_auto_mode_uses_colors_in_development(self, monkeypatch) -> None:
        """FR-030: auto color mode enables colors in development."""
        captured: dict[str, object] = {}
        original = structlog.dev.ConsoleRenderer

        def _capture_console_renderer(*, colors: bool = True, force_colors: bool = False):
            captured["colors"] = colors
            return original(colors=colors, force_colors=force_colors)

        monkeypatch.setattr(structlog.dev, "ConsoleRenderer", _capture_console_renderer)
        monkeypatch.delenv("CI", raising=False)
        settings = ObservabilitySettings(log_format="console", log_color_mode="auto")
        configure_logging(settings, app_env="development", app_debug=False)

        assert captured["colors"] is True

    def test_console_renderer_auto_mode_disables_colors_in_production(self, monkeypatch) -> None:
        """FR-031: auto color mode disables colors in production."""
        captured: dict[str, object] = {}
        original = structlog.dev.ConsoleRenderer

        def _capture_console_renderer(*, colors: bool = True, force_colors: bool = False):
            captured["colors"] = colors
            return original(colors=colors, force_colors=force_colors)

        monkeypatch.setattr(structlog.dev, "ConsoleRenderer", _capture_console_renderer)
        settings = ObservabilitySettings(log_format="console", log_color_mode="auto")
        configure_logging(settings, app_env="production", app_debug=False)

        assert captured["colors"] is False

    def test_console_renderer_auto_mode_disables_colors_in_ci(self, monkeypatch) -> None:
        """FR-031: auto mode disables colors when CI is set."""
        captured: dict[str, object] = {}
        original = structlog.dev.ConsoleRenderer

        def _capture_console_renderer(*, colors: bool = True, force_colors: bool = False):
            captured["colors"] = colors
            return original(colors=colors, force_colors=force_colors)

        monkeypatch.setattr(structlog.dev, "ConsoleRenderer", _capture_console_renderer)
        monkeypatch.setenv("CI", "true")
        settings = ObservabilitySettings(
            log_format="console",
            log_color_mode="auto",
            log_color_disable_in_ci=True,
        )
        configure_logging(settings, app_env="development", app_debug=False)

        assert captured["colors"] is False

    def test_console_renderer_on_mode_keeps_colors_in_ci(self, monkeypatch) -> None:
        """FR-030: explicit on mode forces colors even in CI."""
        captured: dict[str, object] = {}
        original = structlog.dev.ConsoleRenderer

        def _capture_console_renderer(*, colors: bool = True, force_colors: bool = False):
            captured["colors"] = colors
            return original(colors=colors, force_colors=force_colors)

        monkeypatch.setattr(structlog.dev, "ConsoleRenderer", _capture_console_renderer)
        monkeypatch.setenv("CI", "true")
        settings = ObservabilitySettings(
            log_format="console",
            log_color_mode="on",
            log_color_disable_in_ci=True,
        )
        configure_logging(settings, app_env="development", app_debug=False)

        assert captured["colors"] is True


class TestRedactProcessor:
    def test_redacts_password_field(self) -> None:
        """FR-005, FR-006: password field is redacted."""
        processor = RedactProcessor(patterns=["password", "token", "secret"])
        event_dict = {"event": "login", "password": "hunter2", "user": "alice"}
        result = processor(None, None, event_dict)
        assert result["password"] == "***"
        assert result["user"] == "alice"

    def test_redacts_token_field(self) -> None:
        """FR-006: token field is redacted."""
        processor = RedactProcessor(patterns=["password", "token"])
        event_dict = {"event": "auth", "token": "eyJhbGci..."}
        result = processor(None, None, event_dict)
        assert result["token"] == "***"

    def test_redacts_nested_key_case_insensitive(self) -> None:
        """FR-005: redaction is case-insensitive on key names."""
        processor = RedactProcessor(patterns=["password"])
        event_dict = {"event": "test", "Password": "secret123"}
        result = processor(None, None, event_dict)
        assert result["Password"] == "***"

    def test_does_not_redact_non_matching_keys(self) -> None:
        """FR-007: non-matching keys are untouched."""
        processor = RedactProcessor(patterns=["password"])
        event_dict = {"event": "test", "username": "alice", "email": "a@b.com"}
        result = processor(None, None, event_dict)
        assert result["username"] == "alice"
        assert result["email"] == "a@b.com"

    def test_custom_redact_patterns(self) -> None:
        """FR-005: custom patterns are respected."""
        processor = RedactProcessor(patterns=["credit_card"])
        event_dict = {"event": "payment", "credit_card": "4111-1111"}
        result = processor(None, None, event_dict)
        assert result["credit_card"] == "***"

    def test_empty_patterns_no_redaction(self) -> None:
        processor = RedactProcessor(patterns=[])
        event_dict = {"event": "test", "password": "hunter2"}
        result = processor(None, None, event_dict)
        assert result["password"] == "hunter2"


class TestRequestIdProcessor:
    def test_adds_request_id_from_contextvar(self) -> None:
        """FR-017: request_id from ContextVar is added to log entries."""
        from arvel.context.context_store import Context
        from arvel.observability.request_id import request_id_var

        token = request_id_var.set("test-uuid-1234")
        Context.add("request_id", "test-uuid-1234")
        try:
            processor = RequestIdProcessor()
            event_dict: dict[str, object] = {"event": "test"}
            result = processor(None, None, event_dict)
            assert result["request_id"] == "test-uuid-1234"
        finally:
            request_id_var.reset(token)
            Context.forget("request_id")

    def test_no_request_id_when_not_set(self) -> None:
        """FR-017: no request_id when ContextVar is empty."""
        from arvel.context.context_store import Context

        Context.forget("request_id")
        processor = RequestIdProcessor()
        event_dict: dict[str, object] = {"event": "test"}
        result = processor(None, None, event_dict)
        assert "request_id" not in result or result.get("request_id") is None


class TestProcessorPipelineContracts:
    def test_processor_order_is_stable(self) -> None:
        """FR-022: processor order is deterministic and contract-tested."""
        from arvel.observability.logging import _flatten_event

        settings = ObservabilitySettings(log_format="json")
        configure_logging(settings, app_env="development", app_debug=True)

        processors = structlog.get_config().get("processors", [])
        assert len(processors) >= 8

        assert processors[0] is structlog.contextvars.merge_contextvars
        assert processors[1] is structlog.stdlib.add_log_level
        assert processors[2] is structlog.stdlib.add_logger_name
        assert isinstance(processors[3], structlog.processors.TimeStamper)
        assert processors[4] is _flatten_event
        assert isinstance(processors[5], RequestIdProcessor)
        assert isinstance(processors[6], RedactProcessor)
        assert processors[-1] is structlog.stdlib.ProcessorFormatter.wrap_for_formatter

    def test_context_and_request_id_are_injected_before_render(self, capsys) -> None:
        """FR-005, FR-017: contextvars and request_id reach rendered output."""
        from arvel.context.context_store import Context
        from arvel.observability.request_id import request_id_var

        settings = ObservabilitySettings(
            log_format="json",
            log_redact_patterns=("password", "token", "secret"),
        )
        configure_logging(settings, app_env="development", app_debug=True)

        token = request_id_var.set("test-request-id")
        Context.add("request_id", "test-request-id")
        bind_log_context(correlation_id="corr-123")
        try:
            logger = structlog.get_logger("arvel.test.pipeline")
            logger.info("pipeline-event", password="hidden", order_id="ORD-22")
        finally:
            clear_log_context()
            request_id_var.reset(token)
            Context.forget("request_id")

        lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
        payload = json.loads(lines[-1])

        assert payload["event"] == "pipeline-event"
        assert payload["request_id"] == "test-request-id"
        assert payload["correlation_id"] == "corr-123"
        assert payload["password"] == "***"
        assert payload["order_id"] == "ORD-22"


class TestFileChannelDrivers:
    def test_single_channel_writes_to_file(self, tmp_path) -> None:
        """FR-040: single driver writes to configured file path."""
        settings = ObservabilitySettings(
            log_level="info",
            log_format="json",
            log_channels={"single": "single"},
            log_channel_paths={"single": "logs/single.log"},
        )
        configure_logging(
            settings,
            app_env="development",
            app_debug=False,
            base_path=tmp_path,
        )

        logger = structlog.get_logger("arvel.logging.single")
        logger.info("single-file-event")

        log_file = tmp_path / "logs" / "single.log"
        assert log_file.exists()
        payload = json.loads(log_file.read_text().strip().splitlines()[-1])
        assert payload["event"] == "single-file-event"

    def test_daily_channel_uses_timed_rotating_handler(self, tmp_path) -> None:
        """FR-041: daily driver configures timed rotation with retention count."""
        settings = ObservabilitySettings(
            log_level="info",
            log_format="json",
            log_channels={"daily": "daily"},
            log_channel_paths={"daily": "logs/daily.log"},
            log_retention_days=5,
        )
        configure_logging(
            settings,
            app_env="development",
            app_debug=False,
            base_path=tmp_path,
        )

        channel_logger = logging.getLogger("arvel.logging.daily")
        assert len(channel_logger.handlers) == 1
        handler = channel_logger.handlers[0]
        assert isinstance(handler, TimedRotatingFileHandler)
        assert handler.backupCount == 5

    def test_relative_file_path_cannot_escape_base_path(self, tmp_path) -> None:
        """SEC-002: relative file paths cannot escape configured base path."""
        settings = ObservabilitySettings(
            log_level="info",
            log_format="json",
            log_channels={"single": "single"},
            log_channel_paths={"single": "../escape.log"},
        )

        try:
            configure_logging(
                settings,
                app_env="development",
                app_debug=False,
                base_path=tmp_path,
            )
        except ValueError as exc:
            assert "escapes base path" in str(exc)
        else:
            msg = "Expected path escape validation to raise ValueError"
            raise AssertionError(msg)

    def test_stderr_channel_respects_per_channel_level_threshold(self, capsys) -> None:
        """FR-012: per-channel level thresholds filter low-severity events."""
        settings = ObservabilitySettings(
            log_level="debug",
            log_format="json",
            log_channels={"audit": "stderr"},
            log_channel_levels={"audit": "error"},
        )
        configure_logging(settings, app_env="development", app_debug=False)

        logger = structlog.get_logger("arvel.logging.audit")
        logger.info("audit-info-ignored")
        logger.error("audit-error-emitted")

        output_lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
        payloads = [json.loads(line) for line in output_lines]
        events = [payload.get("event") for payload in payloads]

        assert "audit-info-ignored" not in events
        assert "audit-error-emitted" in events
