from __future__ import annotations

from fastapi import FastAPI, Path
from pydantic import BaseModel

from arvel.http import BaseController, route
from arvel.http.router import Router


class UserCreateRequest(BaseModel):
    name: str


class UserResource(BaseModel):
    id: int
    name: str


class _UserController(BaseController):
    prefix = "/users"
    tags = ("users",)
    description = "User management endpoints."
    middleware = ("auth",)

    async def index(self) -> list[UserResource]:
        return [UserResource(id=1, name="Jane")]

    @route.post(
        "/",
        response_model=UserResource,
        summary="Create user",
    )
    async def store(self, payload: UserCreateRequest) -> UserResource:
        return UserResource(id=2, name=payload.name)

    @route.get(
        "/{id}",
        without_middleware=["auth"],
        response_model=UserResource,
        summary="Get user",
    )
    async def show(self, user_id: int = Path(alias="id")) -> UserResource:
        return UserResource(id=user_id, name=f"User {user_id}")


def _build_app(router: Router) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def test_controller_registers_decorated_and_resource_routes() -> None:
    router = Router()
    router.controller(_UserController)

    by_name = {route.name: route for route in router.route_entries if route.name is not None}
    assert by_name["user.index"].path == "/users"
    assert by_name["user.store"].path == "/users"
    assert by_name["user.show"].path == "/users/{id}"
    assert by_name["user.index"].middleware == ["auth"]
    assert by_name["user.show"].without_middleware == ["auth"]


def test_controller_openapi_merges_class_and_method_docs() -> None:
    router = Router()
    router.controller(_UserController)
    app = _build_app(router)

    openapi = app.openapi()
    index_op = openapi["paths"]["/users"]["get"]
    store_op = openapi["paths"]["/users"]["post"]

    assert index_op["tags"] == ["users"]
    assert index_op["description"] == "User management endpoints."
    assert index_op["operationId"] == "user_index"
    assert store_op["summary"] == "Create user"

    request_schema = store_op["requestBody"]["content"]["application/json"]["schema"]
    response_schema = store_op["responses"]["200"]["content"]["application/json"]["schema"]
    assert request_schema["$ref"].endswith("/UserCreateRequest")
    assert response_schema["$ref"].endswith("/UserResource")
