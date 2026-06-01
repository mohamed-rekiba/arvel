"""Web routes — HTML / form-friendly endpoints.

Routes registered here become reachable on the FastAPI app via the root
``Router``. Add controllers via ``arvel make:controller`` (lands with
).
"""

from __future__ import annotations

from arvel import Route


@Route.get("/", name="home")
async def index() -> dict[str, str]:
    return {"message": "Welcome to Arvel"}
