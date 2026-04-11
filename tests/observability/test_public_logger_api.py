"""QA-pre contract tests for public logger facade (Epic 001)."""

from __future__ import annotations

import importlib
import json

import pytest

from arvel.observability.config import ObservabilitySettings
from arvel.observability.logging import configure_logging


@pytest.fixture(autouse=True)
def _reset_log_channels(request: pytest.FixtureRequest) -> None:
    logger_module = importlib.import_module("arvel.logging")
    logger_module.reset_channels()
    request.addfinalizer(logger_module.reset_channels)


def test_public_logger_module_is_importable_from_arvel_logging() -> None:
    """FR-001: Public logger module exists at arvel.logging."""
    logger_module = importlib.import_module("arvel.logging")
    assert logger_module is not None


def test_public_logger_exposes_log_facade() -> None:
    """FR-001: Public logger module exports Log facade."""
    logger_module = importlib.import_module("arvel.logging")
    assert hasattr(logger_module, "Log")


def test_log_facade_exposes_expected_level_methods() -> None:
    """FR-002: Log facade exposes common level methods."""
    logger_module = importlib.import_module("arvel.logging")
    log = logger_module.Log

    for method_name in ("debug", "info", "warning", "error", "critical"):
        assert hasattr(log, method_name)


def test_log_channel_selection_returns_logger_like_interface() -> None:
    """FR-003: channel selection returns an object supporting level methods."""
    logger_module = importlib.import_module("arvel.logging")
    channel_logger = logger_module.Log.channel("stderr")

    assert hasattr(channel_logger, "info")
    assert hasattr(channel_logger, "error")


def test_log_channel_selection_raises_for_unknown_channel() -> None:
    """FR-003: unknown channels raise explicit error."""
    logger_module = importlib.import_module("arvel.logging")
    logger_module.reset_channels()

    with pytest.raises(logger_module.UnknownLogChannelError, match="Unknown log channel"):
        logger_module.Log.channel("audit")


def test_log_channel_selection_uses_configured_channels(capsys) -> None:
    """FR-004: configured channels are selectable and emit channel metadata."""
    settings = ObservabilitySettings(
        log_level="debug",
        log_format="console",
        log_channels={"stderr": "stderr", "audit": "stderr"},
        log_redact_patterns=("password", "token", "secret"),
    )
    configure_logging(settings, app_env="development", app_debug=True)

    logger_module = importlib.import_module("arvel.logging")
    logger_module.configure_channels(
        default_channel="app",
        channels={"app": "stderr", "audit": "stderr"},
    )
    logger_module.Log.channel("audit").info("audit-event")

    captured = capsys.readouterr()
    output = captured.err or captured.out
    assert "audit-event" in output
    assert "audit" in output


def test_log_with_context_redacts_sensitive_fields(capsys) -> None:
    """NFR-002: Public logger keeps redaction enabled for secret-like keys."""
    settings = ObservabilitySettings(
        log_level="debug",
        log_format="console",
        log_redact_patterns=("password", "token", "secret"),
    )
    configure_logging(settings, app_env="development", app_debug=True)

    logger_module = importlib.import_module("arvel.logging")
    logger_module.Log.with_context(password="super-secret", order_id="ORD-1").info("created order")

    output = capsys.readouterr().out
    assert "created order" in output
    assert "ORD-1" in output
    assert "***" in output
    assert "super-secret" not in output


def test_configure_channels_rejects_missing_default_channel() -> None:
    """FR-003: invalid channel configuration fails fast."""
    logger_module = importlib.import_module("arvel.logging")

    with pytest.raises(
        logger_module.InvalidLogChannelConfigurationError,
        match="default_channel 'app' is not present in channels",
    ):
        logger_module.configure_channels(default_channel="app", channels={"stderr": "stderr"})


def test_scoped_log_context_adds_fields_inside_scope_only(capsys) -> None:
    """FR-005: scoped context is applied inside the block and restored after."""
    settings = ObservabilitySettings(
        log_level="debug",
        log_format="json",
        log_redact_patterns=("password", "token", "secret"),
    )
    configure_logging(settings, app_env="development", app_debug=True)
    logger_module = importlib.import_module("arvel.logging")

    with logger_module.scoped_log_context(correlation_id="req-123"):
        logger_module.Log.info("inside-scope")
    logger_module.Log.info("outside-scope")

    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    inside_event = json.loads(lines[-2])
    outside_event = json.loads(lines[-1])

    assert inside_event["event"] == "inside-scope"
    assert inside_event["correlation_id"] == "req-123"
    assert outside_event["event"] == "outside-scope"
    assert "correlation_id" not in outside_event
