"""Prometheus metrics endpoint — /_metrics with CIDR guard."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, Request, Response

from arvel.observability.forwarded import ip_in_cidrs, resolve_client_ip

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


def add_metrics_route(
    app: FastAPI,
    *,
    path: str = "/_metrics",
    allowed_cidrs: list[str] | None = None,
    trusted_proxies: list[str] | None = None,
) -> None:
    """Register a Prometheus text-format metrics endpoint at ``path``.

    Access is restricted to IPs in ``allowed_cidrs`` (loopback by default). The
    client IP is the TCP peer; ``X-Forwarded-For`` is honored only when the peer
    is in ``trusted_proxies``, otherwise a spoofed header could pass the guard.
    """
    if allowed_cidrs is None:
        allowed_cidrs = ["127.0.0.1/32", "::1/128"]

    _cidrs = list(allowed_cidrs)
    _trusted = list(trusted_proxies or [])

    async def metrics_endpoint(request: Request) -> Response:
        peer = request.client.host if request.client else "127.0.0.1"
        ip = resolve_client_ip(
            peer_ip=peer,
            forwarded_for=request.headers.get("X-Forwarded-For"),
            trusted_proxies=_trusted,
        )
        if not ip_in_cidrs(ip, _cidrs):
            return Response(content="Forbidden", status_code=403)

        if _prometheus_available and _prometheus_generate_latest is not None:
            body = _prometheus_generate_latest()
            return Response(content=body, media_type=_prometheus_content_type)

        return Response(content="# prometheus_client not available\n", media_type="text/plain")

    app.add_api_route(path, metrics_endpoint, methods=["GET"], include_in_schema=False)


__all__ = ["add_metrics_route"]
