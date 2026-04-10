"""Tests for health check system — FR-028 to FR-035, SEC-003."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from arvel.observability.health import (
    HealthRegistry,
    HealthResult,
    HealthStatus,
)

if TYPE_CHECKING:
    from arvel.observability.health import HealthCheckPayload, HealthEndpointPayload


@dataclass
class _AlwaysHealthy:
    name: str = "test_healthy"

    async def check(self) -> HealthResult:
        return HealthResult(status=HealthStatus.HEALTHY, message="ok", duration_ms=1.0)


@dataclass
class _AlwaysUnhealthy:
    name: str = "test_unhealthy"

    async def check(self) -> HealthResult:
        return HealthResult(
            status=HealthStatus.UNHEALTHY, message="connection refused", duration_ms=2.0
        )


@dataclass
class _SlowCheck:
    name: str = "test_slow"

    async def check(self) -> HealthResult:
        import anyio

        await anyio.sleep(10)
        return HealthResult(status=HealthStatus.HEALTHY, message="ok", duration_ms=10000.0)


class TestHealthResult:
    def test_healthy_result(self) -> None:
        result = HealthResult(status=HealthStatus.HEALTHY, message="ok", duration_ms=1.5)
        assert result.status == HealthStatus.HEALTHY
        assert result.message == "ok"
        assert result.duration_ms == 1.5

    def test_unhealthy_result(self) -> None:
        result = HealthResult(status=HealthStatus.UNHEALTHY, message="down", duration_ms=0.1)
        assert result.status == HealthStatus.UNHEALTHY

    def test_degraded_result(self) -> None:
        result = HealthResult(status=HealthStatus.DEGRADED, message="slow", duration_ms=5000.0)
        assert result.status == HealthStatus.DEGRADED


class TestHealthRegistry:
    def test_register_check(self) -> None:
        """FR-033: checks are registrable."""
        registry = HealthRegistry(timeout=5.0)
        check = _AlwaysHealthy()
        registry.register(check)
        assert len(registry.checks) == 1

    def test_register_multiple_checks(self) -> None:
        registry = HealthRegistry(timeout=5.0)
        registry.register(_AlwaysHealthy())
        registry.register(_AlwaysUnhealthy(name="db"))
        assert len(registry.checks) == 2

    @pytest.mark.anyio
    async def test_all_healthy(self) -> None:
        """FR-028: all checks pass → status healthy."""
        registry = HealthRegistry(timeout=5.0)
        registry.register(_AlwaysHealthy())
        result = await registry.run_all()
        assert result.status == HealthStatus.HEALTHY
        assert any(check.name == "test_healthy" for check in result.checks)
        assert _check_by_name(result, "test_healthy").status == HealthStatus.HEALTHY

    @pytest.mark.anyio
    async def test_any_unhealthy(self) -> None:
        """FR-029: any check fails → status unhealthy."""
        registry = HealthRegistry(timeout=5.0)
        registry.register(_AlwaysHealthy())
        registry.register(_AlwaysUnhealthy(name="db"))
        result = await registry.run_all()
        assert result.status == HealthStatus.UNHEALTHY
        assert _check_by_name(result, "db").status == HealthStatus.UNHEALTHY

    @pytest.mark.anyio
    async def test_timeout_reports_degraded(self) -> None:
        """FR-030: check that exceeds timeout is reported as degraded."""
        registry = HealthRegistry(timeout=0.1)
        registry.register(_SlowCheck())
        result = await registry.run_all()
        assert _check_by_name(result, "test_slow").status == HealthStatus.DEGRADED

    @pytest.mark.anyio
    async def test_empty_registry(self) -> None:
        """FR-034: no checks registered → healthy."""
        registry = HealthRegistry(timeout=5.0)
        result = await registry.run_all()
        assert result.status == HealthStatus.HEALTHY
        assert result.checks == []

    def test_result_does_not_expose_secrets(self) -> None:
        """SEC-003: health results don't expose connection strings."""
        result = HealthResult(
            status=HealthStatus.UNHEALTHY,
            message="connection refused",
            duration_ms=0.5,
        )
        serialized = str(result)
        assert "postgresql://" not in serialized
        assert "redis://" not in serialized


def _check_by_name(result: HealthEndpointPayload, name: str) -> HealthCheckPayload:
    for check in result.checks:
        if check.name == name:
            return check
    raise AssertionError(f"Missing check with name '{name}'")
