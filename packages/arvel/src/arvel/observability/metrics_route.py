"""Prometheus metrics endpoint — /_metrics with CIDR guard."""

from __future__ import annotations

import ipaddress
from collections.abc import Callable

from fastapi import FastAPI, Request, Response

_prometheus_available: bool = False
_prometheus_content_type: str = "text/plain; version=0.0.4"
_prometheus_generate_latest: Callable[[], bytes] | None = None

try:
    from prometheus_client import CONTENT_TYPE_LATEST
    from prometheus_client import generate_latest as _gl

    _prometheus_available = True
    _prometheus_content_type = CONTENT_TYPE_LATEST
    _prometheus_generate_latest = _gl
except ImportError:
    pass


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "127.0.0.1"


def _is_allowed(ip: str, allowed_cidrs: list[str]) -> bool:
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


def add_metrics_route(
    app: FastAPI,
    *,
    path: str = "/_metrics",
    allowed_cidrs: list[str] | None = None,
) -> None:
    """Register a Prometheus text-format metrics endpoint at ``path``.

    Access is restricted to IPs in ``allowed_cidrs``. Defaults to loopback only.
    """
    if allowed_cidrs is None:
        allowed_cidrs = ["127.0.0.1/32", "::1/128"]

    _cidrs = list(allowed_cidrs)

    async def metrics_endpoint(request: Request) -> Response:
        ip = _client_ip(request)
        if not _is_allowed(ip, _cidrs):
            return Response(content="Forbidden", status_code=403)

        if _prometheus_available and _prometheus_generate_latest is not None:
            body = _prometheus_generate_latest()
            return Response(content=body, media_type=_prometheus_content_type)

        return Response(content="# prometheus_client not available\n", media_type="text/plain")

    app.add_api_route(path, metrics_endpoint, methods=["GET"], include_in_schema=False)


__all__ = ["add_metrics_route"]
