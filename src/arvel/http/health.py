"""Liveness & readiness HTTP probes (DR-0039).

``/livez`` is a cheap *liveness* check — the process is up, no dependency I/O — so a flapping
database never triggers a pod restart. ``/health`` / ``/readyz`` are *readiness*: they run the
registered resources' health checks (the same ``ResourceManager`` the startup gate uses) in parallel
and return ``503`` when a **critical** resource is down (a degraded non-critical one stays ``200``).
"""

from __future__ import annotations

from typing import Any

from arvel.http.response import Response
from arvel.http.response import json as json_response


async def liveness(_request: Any = None) -> Response:
    """Process-is-alive. No dependency checks — always ``200`` while the worker can serve."""
    return json_response({"status": "ok"})


async def readiness(_request: Any = None) -> Response:
    """Readiness: check every registered resource concurrently and report the aggregate. ``200``
    when nothing critical has failed (degraded non-criticals included), ``503`` otherwise."""
    from arvel.kernel import app

    report = await app().resources.check_all()
    body = {
        "status": str(report.status),
        "healthy": report.healthy,
        "resources": {
            name: {
                "status": str(result.status),
                "latency_ms": round(result.latency_ms, 1),
                "detail": result.detail,
            }
            for name, result in report.results.items()
        },
    }
    return json_response(body, status=200 if report.healthy else 503)
