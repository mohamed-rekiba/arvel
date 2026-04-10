"""ObservabilityProvider — boots logging, request-ID, health, tracing, Sentry.

Health checks are registered only for services that are actually enabled.
No-op / in-memory drivers (``null``, ``memory``, ``sync``, ``sqlite``) don't
produce external connections, so there's nothing to probe.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Response, status  # noqa: TC002

from arvel.cache.config import CacheSettings
from arvel.foundation.config import get_module_settings
from arvel.foundation.provider import ServiceProvider
from arvel.http import Router
from arvel.logging import Log
from arvel.logging.channels import configure_channels
from arvel.observability.config import ObservabilitySettings
from arvel.observability.health import HealthEndpointPayload, HealthRegistry, HealthStatus
from arvel.observability.integration_health import (
    CacheHealthCheck,
    DatabaseHealthCheck,
    QueueHealthCheck,
    StorageHealthCheck,
)
from arvel.observability.logging import configure_logging
from arvel.observability.sentry import configure_sentry
from arvel.observability.tracing import configure_tracing
from arvel.queue.config import QueueSettings
from arvel.storage.config import StorageSettings

if TYPE_CHECKING:
    from arvel.foundation.application import Application
    from arvel.foundation.container import ContainerBuilder

logger = Log.named("arvel.observability.provider")

_NOOP_CACHE_DRIVERS = {"memory", "null"}
_NOOP_QUEUE_DRIVERS = {"sync", "null"}
_NOOP_STORAGE_DRIVERS = {"null"}


class ObservabilityProvider(ServiceProvider):
    """Framework-level provider for the observability stack.

    Priority 5 — boots before HTTP (10) so logging is available early.
    """

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

        registry = self._build_health_registry(settings)
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
    def _build_health_registry(settings: ObservabilitySettings) -> HealthRegistry:
        """Register health checks only for services that are actually enabled.

        No-op / in-memory drivers don't have external connections to probe,
        so they're excluded.  Database and local-storage always register
        because they can genuinely fail (file missing, permissions, etc.).
        """
        registry = HealthRegistry(timeout=settings.health_timeout)

        registry.register(DatabaseHealthCheck())

        try:
            cache = CacheSettings()
            if cache.driver not in _NOOP_CACHE_DRIVERS:
                registry.register(CacheHealthCheck())
        except Exception:  # pragma: no cover
            logger.debug("cache_health_skipped", reason="CacheSettings unavailable")

        try:
            queue = QueueSettings()
            if queue.driver not in _NOOP_QUEUE_DRIVERS:
                registry.register(QueueHealthCheck())
        except Exception:  # pragma: no cover
            logger.debug("queue_health_skipped", reason="QueueSettings unavailable")

        try:
            storage = StorageSettings()
            if storage.driver not in _NOOP_STORAGE_DRIVERS:
                registry.register(StorageHealthCheck())
        except Exception:  # pragma: no cover
            logger.debug("storage_health_skipped", reason="StorageSettings unavailable")

        return registry
