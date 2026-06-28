"""T4.4 — routing: registrar, groups, named URLs, compile onto the HTTP kernel."""

from __future__ import annotations

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.routing import Router


async def index(request: object) -> dict[str, bool]:
    return {"ok": True}


async def show(request: object, item_id: str) -> dict[str, str]:
    return {"id": item_id}


def test_register_routes() -> None:
    r = Router()
    r.get("/", index, name="home")
    r.post("/items", index, name="items.store")
    routes = r.routes()
    assert len(routes) == 2
    assert routes[0].methods == ["GET"]
    assert routes[1].methods == ["POST"]


def test_group_applies_prefix_and_name() -> None:
    r = Router()
    with r.group(prefix="/api", name="api."):
        r.get("/users", index, name="users")
    route = r.routes()[0]
    assert route.path == "/api/users"
    assert route.name == "api.users"


def test_named_url_generation() -> None:
    r = Router()
    r.get("/items/{item_id}", show, name="items.show")
    assert r.url("items.show", item_id=7) == "/items/7"


def test_match_and_any_bind_multiple_verbs() -> None:
    r = Router()
    r.match(["GET", "POST"], "/x", index)
    r.any("/y", index)
    assert r.routes()[0].methods == ["GET", "POST"]
    assert {"GET", "POST", "PUT", "PATCH", "DELETE"} <= set(r.routes()[1].methods)


def test_match_route_responds_to_each_verb() -> None:
    r = Router()
    r.match(["GET", "POST"], "/x", index)
    kernel = HttpKernel()
    r.apply_to(kernel)
    with TestClient(app=kernel.build()) as client:
        assert client.get("/x").is_success  # 200
        assert client.post("/x").is_success  # Litestar defaults POST to 201


def test_apply_to_kernel_serves_routes() -> None:
    r = Router()
    r.get("/ping", index)
    r.get("/items/{item_id}", show)
    kernel = HttpKernel()
    r.apply_to(kernel)
    with TestClient(app=kernel.build()) as client:
        assert client.get("/ping").json() == {"ok": True}
        assert client.get("/items/9").json() == {"id": "9"}
