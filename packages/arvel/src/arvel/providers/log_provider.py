"""LogServiceProvider — wires LogManager into the container and binds the Log facade."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from arvel.console._subsystem import CliSubsystem
from arvel.providers.service_provider import ServiceProvider

if TYPE_CHECKING:
    from arvel.logging.manager import LogManager


class LogServiceProvider(ServiceProvider):
    subsystem: ClassVar[CliSubsystem | None] = CliSubsystem.LOG

    def register(self) -> None:
        from arvel.logging.facade import Log
        from arvel.logging.manager import LogManager

        manager = _build_manager()
        self.container.instance(LogManager, manager)
        Log.bind(manager)

        # Push ObservabilityConfig redact list into OtelLogger so it doesn't
        # have to hit the env on every emit when the config is already loaded.
        _configure_otel_redact(self.container)

    async def shutdown(self) -> None:
        from arvel.logging.facade import Log

        Log.unbind()


def _build_manager() -> LogManager:
    """Build a LogManager from config/logging.py, or fall back to otel-only."""
    from arvel.config._lookup_registry import _REGISTRY  # pyright: ignore[reportPrivateUsage]
    from arvel.logging.manager import LogManager

    log_mod = _REGISTRY.get("logging")
    if log_mod is None:
        return LogManager(default="otel", channels={"otel": {"driver": "otel"}})

    try:
        default: str = str(getattr(log_mod, "default", "otel"))
        raw_channels: Any = getattr(log_mod, "channels", {})
        channels: dict[str, dict[str, Any]] = {str(k): dict(v) for k, v in raw_channels.items()}
        return LogManager(default=default, channels=channels)
    except AttributeError, TypeError, ValueError:
        return LogManager(default="otel", channels={"otel": {"driver": "otel"}})


def _configure_otel_redact(container: object) -> None:
    try:
        from arvel.container import Container
        from arvel.logging.otel_logger import configure_redact_fields
        from arvel.observability.config import ObservabilityConfig

        if not isinstance(container, Container):
            return
        if container.bound(ObservabilityConfig):
            obs_cfg = container.make(ObservabilityConfig)
            configure_redact_fields(obs_cfg.log_redact_fields)
    except ImportError, AttributeError:
        pass


__all__ = ["LogServiceProvider"]
