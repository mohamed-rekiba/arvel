"""Bootstrap health endpoint — aggregates every registered ``BaseService``.

``GET /_health`` runs all services' ``health_check()`` concurrently and returns:

- 200 ``{"status": "healthy", "checks": {...}}``   when all healthy
- 200 ``{"status": "degraded", "checks": {...}}``  when some degraded, none unhealthy
- 503 ``{"status": "unhealthy", "checks": {...}}``  when any unhealthy

Each check is bounded by a 5s timeout; a timeout reports ``unhealthy`` with
``detail="timeout"``. Access can be restricted by CIDR.
"""

from __future__ import annotations

import asyncio
import ipaddress
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from arvel.application import Application
from arvel.services import HealthResult, HealthStatus

if TYPE_CHECKING:
    from arvel.container import Container
    from arvel.services import BaseService

_CHECK_TIMEOUT_SECONDS = 5.0
_HTTP_OK = 200
_HTTP_FORBIDDEN = 403
_HTTP_UNAVAILABLE = 503


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "127.0.0.1"


def _is_allowed(ip: str, allowed_cidrs: list[str]) -> bool:
    if not allowed_cidrs:
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for cidr in allowed_cidrs:
        try:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


async def _check_one(service: BaseService) -> tuple[str, HealthResult]:
    try:
        result = await asyncio.wait_for(service.health_check(), timeout=_CHECK_TIMEOUT_SECONDS)
    except TimeoutError:
        return service.name, HealthResult(HealthStatus.unhealthy, "timeout")
    except Exception as exc:  # noqa: BLE001 — a failing probe means unhealthy, never a 500
        return service.name, HealthResult(HealthStatus.unhealthy, str(exc))
    return service.name, result


def _aggregate(results: list[tuple[str, HealthResult]]) -> HealthStatus:
    statuses = {r.status for _, r in results}
    if HealthStatus.unhealthy in statuses:
        return HealthStatus.unhealthy
    if HealthStatus.degraded in statuses:
        return HealthStatus.degraded
    return HealthStatus.healthy


def add_health_route(
    app: FastAPI,
    *,
    container: Container,
    path: str = "/_health",
    allowed_cidrs: list[str] | None = None,
) -> None:
    """Register the aggregated health endpoint at ``path``."""
    cidrs = list(allowed_cidrs or [])

    async def health_endpoint(request: Request) -> JSONResponse:
        if not _is_allowed(_client_ip(request), cidrs):
            return JSONResponse({"detail": "Forbidden"}, status_code=_HTTP_FORBIDDEN)

        services = _resolve_services(container)
        results = await asyncio.gather(*(_check_one(s) for s in services))

        overall = _aggregate(results)
        checks: dict[str, dict[str, str | None]] = {
            name: {"status": str(result.status), "detail": result.detail}
            for name, result in results
        }
        status_code = _HTTP_UNAVAILABLE if overall is HealthStatus.unhealthy else _HTTP_OK
        return JSONResponse(
            {"status": overall.value, "checks": checks},
            status_code=status_code,
        )

    app.add_api_route(path, health_endpoint, methods=["GET"], include_in_schema=False)


def _resolve_services(container: Container) -> list[BaseService]:
    application = container.make(Application)
    return application.services()


__all__ = ["add_health_route"]
