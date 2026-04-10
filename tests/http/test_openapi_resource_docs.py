"""Regression tests for resource controller OpenAPI signatures."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel
from starlette.testclient import TestClient

from arvel.foundation.container import ContainerBuilder
from arvel.http.request import RequestContainerMiddleware
from arvel.http.router import Router


class ItemCreateRequest(BaseModel):
    name: str


class ItemResponse(BaseModel):
    id: int
    name: str


class _ItemController:
    async def store(self, payload: ItemCreateRequest) -> ItemResponse:
        return ItemResponse(id=1, name=payload.name)


class ItemCreatedResponse(BaseModel):
    id: int
    name: str
    status: str


def _build_app(router: Router) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def test_resource_openapi_uses_typed_body_and_response() -> None:
    router = Router()
    router.resource("items", _ItemController, only=["store"])
    app = _build_app(router)

    openapi = app.openapi()
    operation = openapi["paths"]["/items"]["post"]

    params = operation.get("parameters", [])
    assert all(param["name"] != "self" for param in params)

    request_schema = operation["requestBody"]["content"]["application/json"]["schema"]
    assert request_schema["$ref"].endswith("/ItemCreateRequest")

    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema["$ref"].endswith("/ItemResponse")


def test_resource_handler_executes_without_self_query_param() -> None:
    router = Router()
    router.resource("items", _ItemController, only=["store"])
    app = _build_app(router)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/items", json={"name": "Widget"})
    assert response.status_code == 200
    assert response.json() == {"id": 1, "name": "Widget"}


def test_resource_falls_back_when_controller_is_not_bound_in_di() -> None:
    router = Router()
    router.resource("items", _ItemController, only=["store"])
    app = _build_app(router)

    # Simulate real runtime with request-scoped container but without
    # an explicit User/Item controller binding.
    RequestContainerMiddleware.install(app, ContainerBuilder().build())
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/items", json={"name": "Fallback"})
    assert response.status_code == 200
    assert response.json() == {"id": 1, "name": "Fallback"}


def test_route_docs_metadata_is_forwarded_to_openapi() -> None:
    router = Router()

    async def create_item(payload: ItemCreateRequest) -> dict[str, object]:
        return {"id": 10, "name": payload.name, "status": "created"}

    router.post(
        "/items",
        create_item,
        response_model=ItemCreatedResponse,
        responses={400: {"description": "Bad Request"}},
        summary="Create item",
        description="Creates an item and returns metadata.",
        tags=["items"],
        operation_id="items_create",
    )
    app = _build_app(router)

    openapi = app.openapi()
    operation = openapi["paths"]["/items"]["post"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]

    assert operation["summary"] == "Create item"
    assert operation["description"] == "Creates an item and returns metadata."
    assert operation["tags"] == ["items"]
    assert operation["operationId"] == "items_create"
    assert operation["responses"]["400"]["description"] == "Bad Request"
    assert response_schema["$ref"].endswith("/ItemCreatedResponse")
