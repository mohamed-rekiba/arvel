"""Authenticate middleware."""

from __future__ import annotations

from typing import Any, cast

import httpx


class _FakeUser:
    def __init__(self, id: str) -> None:
        self.id = id


def test_authenticate_populates_request_state_user() -> None:
    from arvel import Container
    from arvel.auth.manager import AuthManager
    from arvel.http.auth import Guard
    from arvel.http.exceptions import HttpExceptionHandler
    from arvel.http.middleware import Authenticate
    from arvel.routing import Route, Router
    from fastapi import FastAPI, Request
    from starlette.testclient import TestClient

    Router.reset_singleton()

    container = Container()
    fake = _FakeUser(id="u-1")

    class GuardImpl(Guard):
        async def user(self, request: Any) -> Any | None:
            return fake

    guard_impl = GuardImpl()
    manager = AuthManager(guards={"web": guard_impl}, default="web")
    container.instance(AuthManager, manager)

    with Route.group(middleware=[Authenticate("web")]):

        @Route.get("/me")
        async def me(request: Request) -> dict[str, str]:
            user = request.state.user
            return {"id": user.id}

    del me  # registered via @Route.get; drop local binding
    app = FastAPI()
    HttpExceptionHandler().register(app)
    Router.singleton().register_with_app(app)
    app.state.arvel_container = container
    resp = cast("httpx.Client", TestClient(app)).get("/me")
    assert resp.status_code == 200
    assert resp.json() == {"id": "u-1"}


def test_authenticate_raises_401_when_guard_returns_none() -> None:
    from arvel import Container
    from arvel.auth.manager import AuthManager
    from arvel.http.auth import Guard
    from arvel.http.exceptions import HttpExceptionHandler
    from arvel.http.middleware import Authenticate
    from arvel.routing import Route, Router
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    Router.reset_singleton()

    container = Container()

    class GuardImpl(Guard):
        async def user(self, request: Any) -> Any | None:
            return None

    guard_impl = GuardImpl()
    manager = AuthManager(guards={"web": guard_impl}, default="web")
    container.instance(AuthManager, manager)

    with Route.group(middleware=[Authenticate("web")]):

        @Route.get("/protected")
        async def protected() -> dict[str, str]:
            return {"secret": "value"}

    del protected  # registered via @Route.get; drop local binding
    app = FastAPI()
    HttpExceptionHandler().register(app)
    Router.singleton().register_with_app(app)
    app.state.arvel_container = container

    resp = cast("httpx.Client", TestClient(app)).get("/protected")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"
