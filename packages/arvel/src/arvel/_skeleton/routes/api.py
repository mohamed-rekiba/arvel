"""API routes — JSON-only endpoints.

Routes registered here become reachable on the FastAPI app via the root
``Router``. Group with ``Route.group(prefix="/api")`` once the project
grows beyond a handful of routes.
"""

from __future__ import annotations

from arvel import Route


@Route.get("/api/healthz", name="api.healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
