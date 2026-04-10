"""ObservabilityProvider — logging, health checks, tracing, Sentry."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import Response, status  # noqa: TC002

from arvel.broadcasting.config import BroadcastSettings
from arvel.cache.config import CacheSettings
from arvel.data.config import DatabaseSettings
from arvel.foundation.config import get_module_settings
from arvel.foundation.provider import ServiceProvider
from arvel.http import Router
from arvel.lock.config import LockSettings
from arvel.logging import Log
from arvel.logging.channels import configure_channels
from arvel.mail.config import MailSettings
from arvel.observability.config import ObservabilitySettings
from arvel.observability.health import HealthEndpointPayload, HealthRegistry, HealthStatus
from arvel.observability.integration_health import (
    BroadcastHealthCheck,
    CacheHealthCheck,
    DatabaseHealthCheck,
    LockHealthCheck,
    MailHealthCheck,
    QueueHealthCheck,
    SearchHealthCheck,
    StorageHealthCheck,
)
from arvel.observability.logging import configure_logging
from arvel.observability.sentry import configure_sentry
from arvel.observability.tracing import configure_tracing
from arvel.queue.config import QueueSettings
from arvel.search.config import SearchSettings
from arvel.storage.config import StorageSettings

if TYPE_CHECKING:
    from arvel.app.config import AppSettings
    from arvel.foundation.application import Application
    from arvel.foundation.container import ContainerBuilder

logger = Log.named("arvel.observability.provider")

_NOOP_CACHE_DRIVERS = {"memory", "null"}
_NOOP_QUEUE_DRIVERS = {"sync", "null"}
_NOOP_STORAGE_DRIVERS = {"null"}
_NOOP_MAIL_DRIVERS = {"log", "null", "array"}
_NOOP_SEARCH_DRIVERS = {"null", "collection", "database"}
_NOOP_BROADCAST_DRIVERS = {"null", "log"}
_NOOP_LOCK_DRIVERS = {"memory", "null"}


class ObservabilityProvider(ServiceProvider):
    """Logging, health, tracing, Sentry. Priority 5 (before HTTP at 10)."""

    priority: int = 5

    async def register(self, container: ContainerBuilder) -> None:
        pass

    async def boot(self, app: Application) -> None:
        config = app.config
        try:
            settings = get_module_settings(config, ObservabilitySettings)
        except Exception:
            settings = ObservabilitySettings()

        configure_logging(
            settings,
            app_env=config.app_env,
            app_debug=config.app_debug,
            base_path=config.base_path,
        )
        configure_channels(
            default_channel=settings.log_default_channel,
            channels=settings.log_channels,
        )

        configure_tracing(settings, app_name=config.app_name, fastapi_app=app.asgi_app())
        configure_sentry(settings)

        registry = self._build_health_registry(config, settings)
        startup_health = await registry.run_all()
        for check in startup_health.checks:
            log_fn = logger.info
            if check.status in {HealthStatus.UNHEALTHY, HealthStatus.DEGRADED}:
                log_fn = logger.warning
            log_fn(
                "integration_health_status",
                check=check.name,
                status=check.status.value,
                duration_ms=check.duration_ms,
                message=check.message,
            )
        logger.info("integration_health_overall", status=startup_health.status.value)

        router = Router()

        async def health_endpoint(response: Response) -> HealthEndpointPayload:
            result = await registry.run_all()
            if result.status == HealthStatus.UNHEALTHY:
                response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return result

        router.get(
            "/health",
            health_endpoint,
            tags=["observability"],
            summary="Framework health endpoint",
            description="Aggregated health checks for framework components.",
            operation_id="observability_health",
            response_model=HealthEndpointPayload,
        )

        app.asgi_app().include_router(router)

        logger.debug("observability_boot_complete")

    @staticmethod
    def _build_health_registry(
        config: AppSettings,
        settings: ObservabilitySettings,
    ) -> HealthRegistry:
        """Register health checks for services with real external connections."""
        registry = HealthRegistry(timeout=settings.health_timeout)

        try:
            db_settings = get_module_settings(config, DatabaseSettings)
        except Exception:
            db_settings = None
        registry.register(DatabaseHealthCheck(settings=db_settings))

        _driver_checks: tuple[
            tuple[type[Any], type[Any], frozenset[str]],
            ...,
        ] = (
            (CacheSettings, CacheHealthCheck, frozenset(_NOOP_CACHE_DRIVERS)),
            (QueueSettings, QueueHealthCheck, frozenset(_NOOP_QUEUE_DRIVERS)),
            (StorageSettings, StorageHealthCheck, frozenset(_NOOP_STORAGE_DRIVERS)),
            (MailSettings, MailHealthCheck, frozenset(_NOOP_MAIL_DRIVERS)),
            (SearchSettings, SearchHealthCheck, frozenset(_NOOP_SEARCH_DRIVERS)),
            (BroadcastSettings, BroadcastHealthCheck, frozenset(_NOOP_BROADCAST_DRIVERS)),
            (LockSettings, LockHealthCheck, frozenset(_NOOP_LOCK_DRIVERS)),
        )

        for settings_cls, check_cls, noop_drivers in _driver_checks:
            _register_driver_health_check(
                registry,
                config,
                settings_cls,
                check_cls,
                noop_drivers,
            )

        return registry


def _register_driver_health_check(
    registry: HealthRegistry,
    config: AppSettings,
    settings_cls: type[Any],
    check_cls: type[Any],
    noop_drivers: frozenset[str],
) -> None:
    """Register a health check if the driver has an external connection."""
    try:
        resolved = get_module_settings(config, settings_cls)
    except Exception:
        resolved = settings_cls()
    try:
        driver = getattr(resolved, "driver", None)
        if driver is not None and driver not in noop_drivers:
            registry.register(check_cls(settings=resolved))
    except Exception as exc:  # pragma: no cover
        logger.debug(
            "health_check_skipped",
            check=check_cls.__name__,
            reason=f"{type(exc).__name__}: {exc}",
        )
