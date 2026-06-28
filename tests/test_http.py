"""T4.3 — HTTP kernel on Litestar: routes, path params, responses, OpenAPI."""

from __future__ import annotations

import litestar
from litestar.testing import TestClient

from arvel.http import HttpKernel, Response


def test_get_route_returns_json() -> None:
    kernel = HttpKernel()

    async def index(request: object) -> dict[str, bool]:
        return {"ok": True}

    kernel.get("/", index)
    with TestClient(app=kernel.build()) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"ok": True}


def test_path_param_injected() -> None:
    kernel = HttpKernel()

    async def show(request: object, item_id: str) -> dict[str, str]:
        return {"id": item_id}

    kernel.get("/items/{item_id}", show)
    with TestClient(app=kernel.build()) as client:
        assert client.get("/items/42").json() == {"id": "42"}


def test_response_object_sets_status() -> None:
    kernel = HttpKernel()

    async def create(request: object) -> Response:
        return Response({"created": True}, status=201)

    kernel.post("/items", create)
    with TestClient(app=kernel.build()) as client:
        response = client.post("/items")
        assert response.status_code == 201
        assert response.json() == {"created": True}


def test_openapi_generated_by_litestar() -> None:
    kernel = HttpKernel()

    async def ping(request: object) -> dict[str, bool]:
        return {"pong": True}

    kernel.get("/ping", ping)
    with TestClient(app=kernel.build()) as client:
        schema = client.get("/schema/openapi.json")
        assert schema.status_code == 200
        assert "/ping" in schema.json()["paths"]


def test_as_asgi_is_litestar_instance() -> None:
    kernel = HttpKernel()

    async def index(request: object) -> dict[str, bool]:
        return {"ok": True}

    kernel.get("/", index)
    assert isinstance(kernel.as_asgi(), litestar.Litestar)
