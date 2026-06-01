"""+ Route facade & route groups."""

from __future__ import annotations

from typing import Any

import pytest


def test_route_get_decorator_returns_callable_unchanged() -> None:
    from arvel.routing import Route, Router

    Router.reset_singleton()

    @Route.get("/users")
    async def handler() -> dict[str, str]:
        return {"ok": "yes"}

    # Decorator returns the original handler (still callable directly in tests).
    assert callable(handler)


@pytest.mark.parametrize("verb", ["get", "post", "put", "patch", "delete", "head", "options"])
def test_route_facade_exposes_every_verb(verb: str) -> None:
    from arvel.routing import Route

    assert callable(getattr(Route, verb))


def test_route_registers_route_with_correct_method_and_path() -> None:
    from arvel.routing import Route, Router

    Router.reset_singleton()

    @Route.get("/users")
    async def index() -> dict[str, Any]:
        return {}

    routes = Router.singleton().routes()
    assert any(r.method == "GET" and r.path == "/users" and r.handler is index for r in routes)


def test_route_name_is_recorded() -> None:
    from arvel.routing import Route, Router

    Router.reset_singleton()

    @Route.get("/users/{id}", name="users.show")
    async def show(id: int) -> dict[str, Any]:
        return {"id": id}

    routes = Router.singleton().routes()
    assert any(r.name == "users.show" and r.handler is show for r in routes)


def test_route_group_applies_prefix_to_inner_routes() -> None:
    from arvel.routing import Route, Router

    Router.reset_singleton()

    with Route.group(prefix="/api/v1"):

        @Route.get("/users")
        async def users() -> dict[str, Any]:
            return {}

    routes = Router.singleton().routes()
    assert any(r.path == "/api/v1/users" and r.handler is users for r in routes)


def test_route_group_applies_middleware_to_inner_routes() -> None:
    from arvel.http.middleware import Throttle
    from arvel.routing import Route, Router

    Router.reset_singleton()

    throttle = Throttle(60)

    with Route.group(prefix="/api", middleware=[throttle]):

        @Route.get("/users")
        async def users() -> dict[str, Any]:
            return {}

    routes = Router.singleton().routes()
    matching = [r for r in routes if r.path == "/api/users" and r.handler is users]
    assert matching
    assert throttle in matching[0].middleware


def test_named_middleware_group_applies_to_route() -> None:
    from arvel.routing import Route, Router

    Router.reset_singleton()
    router = Router.singleton()

    class MarkerMiddleware:
        async def handle(self, request: object, call_next: object) -> object:
            raise AssertionError("not executed in registration test")

    marker = MarkerMiddleware()
    router.middleware_group("api", [marker])

    @Route.get("/users", middleware=["api"])
    async def users() -> dict[str, Any]:
        return {}

    routes = Router.singleton().routes()
    matching = [r for r in routes if r.path == "/users" and r.handler is users]
    assert matching
    assert marker in matching[0].middleware


def test_named_middleware_groups_flatten_nested_groups() -> None:
    from arvel.routing import Route, Router

    Router.reset_singleton()
    router = Router.singleton()

    class FirstMiddleware:
        async def handle(self, request: object, call_next: object) -> object:
            raise AssertionError("not executed in registration test")

    class SecondMiddleware:
        async def handle(self, request: object, call_next: object) -> object:
            raise AssertionError("not executed in registration test")

    first = FirstMiddleware()
    second = SecondMiddleware()
    router.middleware_group("web", [first])
    router.middleware_group("api", ["web", second])

    with Route.group(prefix="/api", middleware=["api"]):

        @Route.get("/users")
        async def users() -> dict[str, Any]:
            return {}

        assert users is not None

    route = next(r for r in Router.singleton().routes() if r.path == "/api/users")
    assert route.middleware == (first, second)


def test_unknown_named_middleware_group_raises_at_registration() -> None:
    from arvel.routing import Route, Router

    Router.reset_singleton()

    def register_route_with_missing_group() -> None:
        async def users() -> dict[str, Any]:
            return {}

        with Route.group(middleware=["missing"]):
            Route.get("/users")(users)

    with pytest.raises(ValueError, match="Unknown middleware group"):
        register_route_with_missing_group()


def test_route_groups_compose_when_nested() -> None:
    from arvel.routing import Route, Router

    Router.reset_singleton()

    with Route.group(prefix="/api/v1"), Route.group(prefix="/admin"):

        @Route.get("/users")
        async def users() -> dict[str, Any]:
            return {}

    routes = Router.singleton().routes()
    assert any(r.path == "/api/v1/admin/users" and r.handler is users for r in routes)


def test_route_group_state_restored_on_exception() -> None:
    from arvel.routing import Route, Router

    Router.reset_singleton()

    with pytest.raises(RuntimeError, match="boom"), Route.group(prefix="/api"):
        raise RuntimeError("boom")

    # After the exception, declaring a route should NOT carry the /api prefix.
    @Route.get("/loose")
    async def loose() -> dict[str, Any]:
        return {}

    routes = Router.singleton().routes()
    assert any(r.path == "/loose" and r.handler is loose for r in routes)
    assert not any(r.path == "/api/loose" for r in routes)


def test_route_group_applies_tags_to_inner_routes() -> None:
    from arvel.routing import Route, Router

    Router.reset_singleton()

    with Route.group(prefix="/api/admin", tags=["Admin Products"]):

        @Route.get("/products")
        async def products() -> dict[str, Any]:
            return {}

    route = next(
        r
        for r in Router.singleton().routes()
        if r.path == "/api/admin/products" and r.handler is products
    )
    assert route.extras["tags"] == ["Admin Products"]


def test_nested_groups_concatenate_tags_and_per_route_tags_append() -> None:
    from arvel.routing import Route, Router

    Router.reset_singleton()

    with Route.group(tags=["Admin"]), Route.group(tags=["Products"]):

        @Route.get("/products", tags=["Catalog"])
        async def products() -> dict[str, Any]:
            return {}

    route = next(
        r for r in Router.singleton().routes() if r.path == "/products" and r.handler is products
    )
    assert route.extras["tags"] == ["Admin", "Products", "Catalog"]


def test_group_tags_surface_in_openapi_schema() -> None:
    from arvel.routing import Route, Router
    from fastapi import FastAPI

    Router.reset_singleton()

    with Route.group(prefix="/api", tags=["Catalog"]):

        @Route.get("/products", name="products.index")
        async def products() -> dict[str, Any]:
            return {}

        assert callable(products)

    app = FastAPI()
    Router.singleton().register_with_app(app)

    operation = app.openapi()["paths"]["/api/products"]["get"]
    assert operation["tags"] == ["Catalog"]
