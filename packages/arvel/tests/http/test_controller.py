"""Controller base + invokable controllers."""

from __future__ import annotations

from typing import Any, cast

import httpx2 as httpx


def test_controller_base_class_exists() -> None:
    from arvel.http.controller import Controller

    class UserController(Controller):
        async def show(self, id: int) -> dict[str, int]:
            return {"id": id}

    assert issubclass(UserController, Controller)


def test_controller_instance_resolved_via_container() -> None:
    from arvel import Container
    from arvel.http.controller import Controller

    class MyController(Controller):
        def __init__(self) -> None:
            self.spies: list[str] = []

        async def index(self) -> dict[str, Any]:
            return {}

    c = Container()
    c.bind(MyController)
    inst = c.make(MyController)
    assert isinstance(inst, MyController)


def test_invokable_controller_dispatches_to_call() -> None:
    import asyncio

    from arvel.http.controller import Controller

    class Dashboard(Controller):
        async def __call__(self) -> dict[str, str]:
            return {"page": "dashboard"}

    result = asyncio.run(Dashboard()())
    assert result == {"page": "dashboard"}


def test_invokable_controller_is_callable_at_route_level() -> None:
    from arvel.http.controller import Controller
    from arvel.routing import Route, Router
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    Router.reset_singleton()

    class Dashboard(Controller):
        async def __call__(self) -> dict[str, str]:
            return {"page": "dashboard"}

    Route.get("/dashboard", controller=Dashboard)

    app = FastAPI()
    Router.singleton().register_with_app(app)
    resp = cast("httpx.Client", TestClient(app)).get("/dashboard")
    assert resp.status_code == 200
    assert resp.json() == {"page": "dashboard"}
