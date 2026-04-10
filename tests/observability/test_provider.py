"""Tests for ObservabilityProvider — FR-001, FR-013 (provider wiring)."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from fastapi import FastAPI

from arvel.foundation.config import AppSettings
from arvel.observability.config import ObservabilitySettings
from arvel.observability.health import HealthCheckPayload, HealthEndpointPayload, HealthStatus
from arvel.observability.integration_health import (
    CacheHealthCheck,
    DatabaseHealthCheck,
    QueueHealthCheck,
)
from arvel.observability.provider import ObservabilityProvider

if TYPE_CHECKING:
    from arvel.foundation.application import Application


class TestObservabilityProvider:
    def test_priority_is_5(self) -> None:
        """D3: ObservabilityProvider boots at priority 5."""
        provider = ObservabilityProvider()
        assert provider.priority == 5

    def test_is_service_provider(self) -> None:
        from arvel.foundation.provider import ServiceProvider

        provider = ObservabilityProvider()
        assert isinstance(provider, ServiceProvider)

    async def test_boot_configures_log_channels_from_settings(self, monkeypatch) -> None:
        """FR-003: boot wires log channel settings into logger registry."""
        provider = ObservabilityProvider()
        app_settings = AppSettings(app_name="TestApp", app_env="development", app_debug=True)
        app_settings._module_settings[ObservabilitySettings] = ObservabilitySettings(
            log_default_channel="app",
            log_channels={"app": "stderr", "audit": "daily"},
        )

        captured: dict[str, object] = {}

        def _capture_channels(*, default_channel: str, channels: dict[str, str]) -> None:
            captured["default_channel"] = default_channel
            captured["channels"] = channels

        monkeypatch.setattr("arvel.observability.provider.configure_channels", _capture_channels)

        class _FakeRegistry:
            def __init__(self, timeout: float = 5.0) -> None:
                self.timeout = timeout
                self.checks: list[object] = []

            def register(self, check: object) -> None:
                self.checks.append(check)

            async def run_all(self) -> HealthEndpointPayload:
                return HealthEndpointPayload(status=HealthStatus.HEALTHY, checks=[])

        monkeypatch.setattr("arvel.observability.provider.HealthRegistry", _FakeRegistry)

        class _FakeApp:
            def __init__(self, config: AppSettings) -> None:
                self.config = config
                self._app = FastAPI()

            def asgi_app(self) -> FastAPI:
                return self._app

        await provider.boot(cast("Application", _FakeApp(app_settings)))

        assert captured["default_channel"] == "app"
        assert captured["channels"] == {"app": "stderr", "audit": "daily"}

    async def test_boot_registers_integration_health_checks(self, monkeypatch) -> None:
        """Boot wires default DB/cache/queue checks into health registry."""
        monkeypatch.setenv("CACHE_DRIVER", "redis")
        monkeypatch.setenv("QUEUE_DRIVER", "taskiq")

        provider = ObservabilityProvider()
        app_settings = AppSettings(app_name="TestApp", app_env="development", app_debug=True)

        class _FakeRegistry:
            last_instance: _FakeRegistry | None = None

            def __init__(self, timeout: float = 5.0) -> None:
                self.timeout = timeout
                self.checks: list[object] = []
                _FakeRegistry.last_instance = self

            def register(self, check: object) -> None:
                self.checks.append(check)

            async def run_all(self) -> HealthEndpointPayload:
                return HealthEndpointPayload(status=HealthStatus.HEALTHY, checks=[])

        monkeypatch.setattr("arvel.observability.provider.HealthRegistry", _FakeRegistry)

        class _FakeApp:
            def __init__(self, config: AppSettings) -> None:
                self.config = config
                self._app = FastAPI()

            def asgi_app(self) -> FastAPI:
                return self._app

        await provider.boot(cast("Application", _FakeApp(app_settings)))

        assert _FakeRegistry.last_instance is not None
        check_types = {type(check) for check in _FakeRegistry.last_instance.checks}
        assert DatabaseHealthCheck in check_types
        assert CacheHealthCheck in check_types
        assert QueueHealthCheck in check_types

    async def test_boot_logs_startup_integration_health_snapshot(self, monkeypatch) -> None:
        """Boot emits per-check and aggregate health status logs."""
        provider = ObservabilityProvider()
        app_settings = AppSettings(app_name="TestApp", app_env="development", app_debug=True)

        class _FakeRegistry:
            def __init__(self, timeout: float = 5.0) -> None:
                self.timeout = timeout
                self.checks: list[object] = []

            def register(self, check: object) -> None:
                self.checks.append(check)

            async def run_all(self) -> HealthEndpointPayload:
                return HealthEndpointPayload(
                    status=HealthStatus.DEGRADED,
                    checks=[
                        HealthCheckPayload(
                            name="database",
                            status=HealthStatus.UNHEALTHY,
                            message="unavailable",
                            duration_ms=9.12,
                        )
                    ],
                )

        class _LoggerStub:
            def __init__(self) -> None:
                self.events: list[str] = []

            def info(self, event: str, **kwargs: object) -> None:
                self.events.append(event)

            def warning(self, event: str, **kwargs: object) -> None:
                self.events.append(event)

            def debug(self, event: str, **kwargs: object) -> None:
                self.events.append(event)

        logger_stub = _LoggerStub()
        monkeypatch.setattr("arvel.observability.provider.HealthRegistry", _FakeRegistry)
        monkeypatch.setattr("arvel.observability.provider.logger", logger_stub)

        class _FakeApp:
            def __init__(self, config: AppSettings) -> None:
                self.config = config
                self._app = FastAPI()

            def asgi_app(self) -> FastAPI:
                return self._app

        await provider.boot(cast("Application", _FakeApp(app_settings)))

        assert "integration_health_status" in logger_stub.events
        assert "integration_health_overall" in logger_stub.events
