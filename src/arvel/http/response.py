"""arvel.http.Response — a light, engine-agnostic response value.

Handlers may return a plain ``dict``/``list``/``str`` (Litestar serializes it) or
an explicit ``Response``; the kernel converts the latter to a ``litestar.Response``
in the serve path (Litestar imported there, not here).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Response:
    content: Any = None
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict[str, str])


def json(content: Any, status: int = 200) -> Response:
    return Response(content=content, status=status)


async def prometheus_metrics(request: Any = None) -> Response:
    """Route handler for the Prometheus scrape endpoint: wraps telemetry's exposition payload in an
    http ``Response``. Lives here (http→telemetry is a legal downward edge) so telemetry need not
    import http; the routing provider registers it at ``/metrics`` when ``telemetry.prometheus`` is on
    (DR-0026)."""
    from arvel.telemetry import prometheus_payload

    content, content_type = prometheus_payload()
    return Response(content=content, headers={"content-type": content_type})
