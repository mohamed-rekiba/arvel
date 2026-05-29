"""FR-002-003 — Router.register_with_app(fastapi) mounts buffered routes."""

from __future__ import annotations

from typing import Any


def test_router_registers_routes_with_fastapi_app() -> None:
    from arvel.routing import Route, Router
    from fastapi import FastAPI
    from starlette.routing import Route as StarletteRoute

    Router.reset_singleton()

    @Route.get("/ping", name="ping")
    async def ping() -> dict[str, Any]:
        return {"pong": True}

    fastapi_app = FastAPI()
    Router.singleton().register_with_app(fastapi_app)

    # Narrow starlette's BaseRoute union to the concrete Route class so .path is typed.
    paths = {r.path for r in fastapi_app.routes if isinstance(r, StarletteRoute)}
    assert "/ping" in paths
    assert any(r.handler is ping for r in Router.singleton().routes())


def test_router_preserves_route_name_for_url_lookup() -> None:
    from arvel.routing import Route, Router
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    Router.reset_singleton()

    @Route.get("/echo/{n}", name="echo")
    async def echo(n: int) -> dict[str, int]:
        return {"n": n}

    assert any(r.handler is echo for r in Router.singleton().routes())
    fastapi_app = FastAPI()
    Router.singleton().register_with_app(fastapi_app)

    client = TestClient(fastapi_app)
    resp = client.get("/echo/42")
    assert resp.status_code == 200
    assert resp.json() == {"n": 42}


def test_router_executes_route_level_middleware() -> None:
    from arvel.routing import Route, Router
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    Router.reset_singleton()

    calls: list[str] = []

    class TrackingMiddleware:
        async def handle(self, request: Any, call_next: Any) -> Any:
            calls.append("before")
            response = await call_next(request)
            calls.append("after")
            return response

    with Route.group(middleware=[TrackingMiddleware()]):

        @Route.get("/tracked")
        async def tracked() -> dict[str, bool]:
            calls.append("handler")
            return {"ok": True}

    assert any(r.handler is tracked for r in Router.singleton().routes())
    fastapi_app = FastAPI()
    Router.singleton().register_with_app(fastapi_app)
    client = TestClient(fastapi_app)
    client.get("/tracked")

    assert calls == ["before", "handler", "after"]
