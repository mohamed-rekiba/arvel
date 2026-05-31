"""Service lifecycle contract — ``BaseService``, health status, health result.

A ``BaseService`` participates in the application's managed lifecycle: ``connect()``
runs during ``Application.boot()`` (in registration order) and ``disconnect()`` runs
during ``Application.shutdown()`` (in reverse). ``health_check()`` feeds the
``/_health`` endpoint.

```python
class RedisService(BaseService):
    name = "redis"

    async def connect(self) -> None:
        self._client = await aioredis.from_url(self._url)

    async def disconnect(self) -> None:
        await self._client.aclose()

    async def health_check(self) -> HealthResult:
        await self._client.ping()
        return HealthResult(HealthStatus.healthy)

app.register_service(RedisService())
```
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum


class HealthStatus(StrEnum):
    healthy = "healthy"
    degraded = "degraded"
    unhealthy = "unhealthy"


@dataclass(frozen=True, slots=True)
class HealthResult:
    """Outcome of a single service health check.

    ``detail`` must never carry connection strings, credentials, or internal
    hostnames — it is surfaced over HTTP.
    """

    status: HealthStatus
    detail: str | None = None


class BaseService(ABC):
    """A managed service with connect/disconnect/health lifecycle hooks.

    Subclasses set ``name`` (used in health output and boot errors) and override
    ``health_check``. ``connect`` and ``disconnect`` default to no-ops so a probe-only
    service doesn't have to implement them.
    """

    name: str = "service"

    async def connect(self) -> None:
        """Acquire resources. Runs during ``Application.boot()``. No-op by default."""
        return

    async def disconnect(self) -> None:
        """Release resources. Runs during ``Application.shutdown()`` (reverse order).

        No-op by default. Override to roll back pending writes so shutdown leaves
        no open transactions.
        """
        return

    @abstractmethod
    async def health_check(self) -> HealthResult:
        """Report current health. Raising is treated as ``unhealthy``."""


__all__ = ["BaseService", "HealthResult", "HealthStatus"]
