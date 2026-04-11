"""Structured logging configuration — structlog setup, processors, renderers."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from arvel.context.context_store import Context

if TYPE_CHECKING:
    from collections.abc import Sequence

    from arvel.observability.config import ObservabilitySettings


def _resolve_console_use_colors(
    settings: ObservabilitySettings,
    *,
    app_env: str,
) -> bool:
    color_mode = settings.log_color_mode
    if color_mode == "on":
        return True
    if color_mode == "off":
        return False

    if app_env == "production":
        return False
    return not (settings.log_color_disable_in_ci and os.getenv("CI"))


def _resolve_log_file_path(*, base_path: Path | None, configured_path: str) -> Path:
    raw = Path(configured_path)
    if raw.is_absolute():
        resolved = raw.resolve()
    else:
        root = (base_path or Path.cwd()).resolve()
        resolved = (root / raw).resolve()
        if not str(resolved).startswith(str(root)):
            raise ValueError(f"Log path escapes base path: {configured_path}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _configure_channel_handlers(
    *,
    settings: ObservabilitySettings,
    formatter: logging.Formatter,
    log_level: int,
    base_path: Path | None,
) -> None:
    def _reset_handlers(target_logger: logging.Logger) -> None:
        for existing_handler in list(target_logger.handlers):
            target_logger.removeHandler(existing_handler)
            existing_handler.close()

    def _channel_log_level(channel_name: str) -> int:
        level_name = settings.log_channel_levels.get(channel_name, settings.log_level)
        return getattr(logging, level_name.upper(), log_level)

    for channel_name, driver in settings.log_channels.items():
        if driver == "stderr":
            channel_handler: logging.Handler = logging.StreamHandler(sys.stderr)
        else:
            configured_path = settings.log_channel_paths.get(driver)
            if configured_path is None:
                continue
            file_path = _resolve_log_file_path(base_path=base_path, configured_path=configured_path)

            if driver == "single":
                channel_handler = logging.FileHandler(file_path, encoding="utf-8")
            else:
                channel_handler = TimedRotatingFileHandler(
                    file_path,
                    when="midnight",
                    backupCount=settings.log_retention_days,
                    encoding="utf-8",
                )

        channel_handler.setFormatter(formatter)
        logger_name = f"arvel.logging.{channel_name}"
        channel_logger = logging.getLogger(logger_name)
        _reset_handlers(channel_logger)
        channel_logger.addHandler(channel_handler)
        channel_logger.setLevel(_channel_log_level(channel_name))
        channel_logger.propagate = False


class SafeBoundLogger(structlog.stdlib.BoundLogger):
    """BoundLogger that catches %-style formatting mismatches.

    ``structlog.stdlib.BoundLogger`` forwards positional args straight to
    stdlib's ``Logger``, which does ``msg % args`` eagerly.  A mismatch
    (wrong number of ``%s`` placeholders) raises ``TypeError`` inside the
    handler's ``emit()`` and produces an ugly ``--- Logging error ---``
    traceback instead of a clean log line.

    This subclass intercepts positional args, applies the formatting
    safely (falling back to concatenation on error), and passes the
    result as a plain event string with no leftover ``args``.
    """

    def _proxy_to_logger(
        self,
        method_name: str,
        event: str | None = None,
        *args: Any,
        **kw: Any,
    ) -> Any:
        if args and event is not None:
            try:
                event = event % args
            except TypeError, ValueError:
                event = f"{event} {' '.join(str(a) for a in args)}"
            args = ()
        return super()._proxy_to_logger(method_name, event, *args, **kw)


class SafeProcessorFormatter(structlog.stdlib.ProcessorFormatter):
    """ProcessorFormatter that never lets a %-style mismatch crash ``emit()``.

    stdlib's ``logging.Handler.emit()`` calls ``self.format(record)``
    which calls ``record.getMessage()`` — and that does ``msg % args``.
    If the caller passed mismatched positional args to a stdlib logger
    (e.g. ``logger.info("x: %s", a, b)``), ``getMessage()`` raises
    ``TypeError`` and the handler prints the ugly
    ``--- Logging error ---`` traceback.

    This subclass patches the record *before* the parent ``format()``
    touches it, resolving the ``msg``/``args`` pair safely.
    """

    def format(self, record: logging.LogRecord) -> str:
        if record.args:
            try:
                record.msg = record.msg % record.args
            except TypeError, ValueError:
                args = record.args if isinstance(record.args, tuple) else (record.args,)
                record.msg = f"{record.msg} {' '.join(str(a) for a in args)}"
            record.args = None
        return super().format(record)


def _flatten_event(
    logger: Any,
    method_name: Any,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Collapse embedded newlines in the ``event`` field to a single space.

    Third-party libraries (e.g. SQLAlchemy echo) may emit multi-line log
    messages.  Structured log lines must stay on one line so they're
    parseable by log aggregators and human-readable in terminals.
    """
    event = event_dict.get("event")
    if isinstance(event, str) and "\n" in event:
        event_dict["event"] = " ".join(event.split())
    return event_dict


class RedactProcessor:
    """structlog processor that redacts sensitive field values.

    Keys matching any pattern (case-insensitive substring match) have their
    values replaced with ``***``.
    """

    def __init__(self, patterns: Sequence[str]) -> None:
        self._patterns = [p.lower() for p in patterns]

    def __call__(
        self,
        logger: Any,
        method_name: Any,
        event_dict: dict[str, Any],
    ) -> dict[str, Any]:
        for key in list(event_dict):
            key_lower = key.lower()
            for pattern in self._patterns:
                if pattern in key_lower:
                    event_dict[key] = "***"
                    break
        return event_dict


class ContextProcessor:
    """structlog processor that merges all ``Context`` keys into the log event.

    Any key stored via ``Context.add(key, value)`` — whether by the
    framework (``request_id``) or by application service providers
    (``tenant_id``, ``user_id``, ``correlation_id``, …) — is injected
    into every structlog event dict automatically.

    Keys already present in the event dict are **not** overwritten, so
    explicit logger kwargs always take precedence.
    """

    def __call__(
        self,
        logger: Any,
        method_name: Any,
        event_dict: dict[str, Any],
    ) -> dict[str, Any]:
        ctx = Context.all()
        for key, value in ctx.items():
            if key not in event_dict:
                event_dict[key] = value
        return event_dict


RequestIdProcessor = ContextProcessor


def configure_logging(
    settings: ObservabilitySettings,
    *,
    app_env: str,
    app_debug: bool,
    base_path: Path | None = None,
) -> None:
    """Configure structlog globally with appropriate renderer and processors.

    Also bridges stdlib logging so third-party libraries using
    ``logging.getLogger()`` flow through structlog processors.
    """
    log_format = settings.log_format
    if log_format == "auto":
        log_format = "json" if app_env == "production" else "console"

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _flatten_event,
        ContextProcessor(),
        RedactProcessor(patterns=settings.log_redact_patterns),
    ]

    if log_format == "json":
        # JSON renderer needs exc_info pre-formatted into a string
        shared_processors.append(structlog.processors.format_exc_info)
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        # ConsoleRenderer formats exceptions natively — adding
        # format_exc_info before it produces a duplicate / warning
        renderer = structlog.dev.ConsoleRenderer(
            colors=_resolve_console_use_colors(settings, app_env=app_env),
        )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=SafeBoundLogger,
        cache_logger_on_first_use=True,
    )

    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    formatter = SafeProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    for existing_handler in list(root_logger.handlers):
        root_logger.removeHandler(existing_handler)
        existing_handler.close()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    _configure_channel_handlers(
        settings=settings,
        formatter=formatter,
        log_level=log_level,
        base_path=base_path,
    )

    noisy_third_party_loggers = (
        "aiobotocore",
        "aiosqlite",
        "asyncio",
        "boto3",
        "botocore",
        "httpcore",
        "httpx",
        "hpack",
        "python_multipart",
        "s3transfer",
        "urllib3",
        "uvicorn",
        "uvicorn.access",
        "watchfiles",
    )
    for name in noisy_third_party_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)
