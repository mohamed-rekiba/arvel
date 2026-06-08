"""Controllers resolve fresh per request (Laravel parity, no state bleed).

Both ``MethodControllerAdapter`` and the invokable-controller adapter used to
instantiate the controller once at route registration and reuse it for every
request. Per-request ``self`` state accumulated across requests (and would race
across concurrent requests in an async process). Laravel resolves the controller
from the container per request; these tests pin that behavior.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import httpx2 as httpx
import pytest
from arvel.container import Container
from arvel.http.controller import Controller
from arvel.routing import MethodControllerAdapter, Route, Router
from fastapi import FastAPI
from starlette.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_router() -> None:
    Router.reset_singleton()


class _CountingCtrl(Controller):
    def __init__(self) -> None:
        self.calls = 0

    async def ping(self) -> dict[str, int]:
        self.calls += 1
        return {"calls": self.calls}


class _CountingInvokable(Controller):
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self) -> dict[str, int]:
        self.calls += 1
        return {"calls": self.calls}


# Method controllers


def test_method_controller_is_fresh_per_request_http() -> None:
    Route.get("/ping", controller=_CountingCtrl, action="ping")

    app = FastAPI()
    Router.singleton().register_with_app(app)

    client = cast("httpx.Client", TestClient(app))
    assert [client.get("/ping").json() for _ in range(3)] == [{"calls": 1}] * 3


def test_method_controller_is_fresh_per_request_unit() -> None:
    handler = MethodControllerAdapter(_CountingCtrl, "ping").build()

    async def _run() -> list[Any]:
        return [await handler(), await handler(), await handler()]

    assert asyncio.run(_run()) == [{"calls": 1}] * 3


# Invokable controllers


def test_invokable_controller_is_fresh_per_request_http() -> None:
    Route.get("/run", controller=_CountingInvokable)

    app = FastAPI()
    Router.singleton().register_with_app(app)

    client = cast("httpx.Client", TestClient(app))
    assert [client.get("/run").json() for _ in range(3)] == [{"calls": 1}] * 3


# DI still works and the per-request instance is genuinely new


def test_fresh_controller_keeps_shared_singleton_dependency() -> None:
    class Repo:
        def __init__(self) -> None:
            self.token = "shared"

    class Ctrl(Controller):
        def __init__(self, repo: Repo) -> None:
            self.repo = repo
            self.seen = 0

        async def show(self) -> dict[str, Any]:
            self.seen += 1
            return {"tok": self.repo.token, "seen": self.seen}

    Route.get("/show", controller=Ctrl, action="show")

    app = FastAPI()
    container = Container()
    container.singleton(Repo)
    app.state.arvel_container = container
    Router.singleton().register_with_app(app)

    client = cast("httpx.Client", TestClient(app))
    results = [client.get("/show").json() for _ in range(3)]
    # Fresh controller each request -> seen always 1; singleton dep stays shared.
    assert results == [{"tok": "shared", "seen": 1}] * 3


def test_controller_bound_as_instance_is_shared_by_choice() -> None:
    """Opting into a shared controller via container.instance() is honored."""

    class SharedCtrl(Controller):
        def __init__(self) -> None:
            self.calls = 0

        async def ping(self) -> dict[str, int]:
            self.calls += 1
            return {"calls": self.calls}

    Route.get("/shared", controller=SharedCtrl, action="ping")

    app = FastAPI()
    container = Container()
    container.instance(SharedCtrl, SharedCtrl())
    app.state.arvel_container = container
    Router.singleton().register_with_app(app)

    client = cast("httpx.Client", TestClient(app))
    # Same object every request because the app explicitly bound an instance.
    assert [client.get("/shared").json() for _ in range(3)] == [
        {"calls": 1},
        {"calls": 2},
        {"calls": 3},
    ]
