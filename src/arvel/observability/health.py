"""Health check system — registry, protocol, and HTTP route factory."""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import anyio
from pydantic import BaseModel


class HealthStatus(enum.StrEnum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class HealthResult:
    """Result of a single health check."""

    status: HealthStatus
    message: str
    duration_ms: float


class HealthCheckPayload(BaseModel):
    """Serialized payload for a single health check."""

    name: str
    status: HealthStatus
    message: str
    duration_ms: float


class HealthEndpointPayload(BaseModel):
    """Serialized aggregate health endpoint payload."""

    status: HealthStatus
    checks: list[HealthCheckPayload]


@runtime_checkable
class HealthCheck(Protocol):
    """Protocol for subsystem health checks."""

    name: str

    async def check(self) -> HealthResult: ...


class HealthRegistry:
    """Collects and runs health checks with per-check timeouts."""

    def __init__(self, timeout: float = 5.0) -> None:
        self._checks: list[HealthCheck] = []
        self._timeout = timeout

    @property
    def checks(self) -> list[HealthCheck]:
        return list(self._checks)

    def register(self, check: HealthCheck) -> None:
        self._checks.append(check)

    async def run_all(self) -> HealthEndpointPayload:
        """Run all registered checks and return aggregate status."""
        results: list[HealthCheckPayload] = []
        overall = HealthStatus.HEALTHY

        for hc in self._checks:
            start = time.monotonic()
            try:
                with anyio.fail_after(self._timeout):
                    result = await hc.check()
            except TimeoutError:
                elapsed = (time.monotonic() - start) * 1000
                result = HealthResult(
                    status=HealthStatus.DEGRADED,
                    message=f"timed out after {self._timeout}s",
                    duration_ms=elapsed,
                )

            results.append(
                HealthCheckPayload(
                    name=hc.name,
                    status=result.status,
                    message=result.message,
                    duration_ms=round(result.duration_ms, 2),
                )
            )

            if result.status == HealthStatus.UNHEALTHY:
                overall = HealthStatus.UNHEALTHY
            elif result.status == HealthStatus.DEGRADED and overall != HealthStatus.UNHEALTHY:
                overall = HealthStatus.DEGRADED

        return HealthEndpointPayload(status=overall, checks=results)
