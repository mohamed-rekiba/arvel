"""Health probes (DR-0039).

``/health`` is the **readiness** probe: it runs every registered resource's health check (the same
``ResourceManager`` the startup gate uses) in parallel and returns ``503`` when a **critical**
resource is down (a degraded non-critical one stays ``200``). It's typed, so the response shape shows
up in the OpenAPI docs. ``/livez`` is a cheap **liveness** probe — the process is up, no dependency
I/O — and is hidden from the schema (an infra endpoint for orchestrators, not part of the API).
"""

from __future__ import annotations

from typing import Any

from arvel.http.response import Response
from arvel.http.response import json as json_response
from arvel.validation import Schema


class ResourceHealth(Schema):
    """One resource's health in the readiness report."""

    status: str
    latency_ms: float
    detail: str | None = None


class HealthReport(Schema):
    """Aggregate readiness across every registered resource."""

    status: str  # worst-case: ok | degraded | failed
    healthy: bool  # false when a critical resource is down (→ 503)
    resources: dict[str, ResourceHealth]


async def health(_request: Any = None) -> HealthReport:
    """Readiness: check every registered resource concurrently. ``200`` when nothing critical has
    failed (degraded non-criticals included), ``503`` otherwise."""
    from arvel.kernel import app

    report = await app().resources.check_all()
    body = HealthReport(
        status=str(report.status),
        healthy=report.healthy,
        resources={
            name: ResourceHealth(
                status=str(result.status),
                latency_ms=round(result.latency_ms, 1),
                detail=result.detail,
            )
            for name, result in report.results.items()
        },
    )
    # annotated `-> HealthReport` so the schema is documented; the Response carries the dynamic
    # 200/503 status (the annotation drives OpenAPI, the returned Response drives the runtime status)
    return json_response(body, status=200 if report.healthy else 503)  # type: ignore[return-value]


async def liveness(_request: Any = None) -> Response:
    """Process-is-alive. No dependency checks — always ``200`` while the worker can serve. Hidden
    from the OpenAPI schema (infra probe)."""
    return json_response({"status": "ok"})
