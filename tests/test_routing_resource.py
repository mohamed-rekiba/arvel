"""C5a — resource/api_resource routes, Controller, fallback."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.routing import Controller, Router


class PostController(Controller):
    async def index(self, request: Any) -> dict[str, Any]:
        return {"action": "index"}

    async def create(self, request: Any) -> dict[str, Any]:
        return {"action": "create"}

    async def store(self, request: Any) -> dict[str, Any]:
        return {"action": "store"}

    async def show(self, request: Any, post: str) -> dict[str, Any]:
        return {"action": "show", "id": post}

    async def edit(self, request: Any, post: str) -> dict[str, Any]:
        return {"action": "edit", "id": post}

    async def update(self, request: Any, post: str) -> dict[str, Any]:
        return {"action": "update", "id": post}

    async def destroy(self, request: Any, post: str) -> dict[str, Any]:
        return {"action": "destroy", "id": post}


def test_resource_registers_seven_named_routes() -> None:
    router = Router()
    router.resource("posts", PostController)
    names = {route.name for route in router.routes()}
    assert names == {
        "posts.index",
        "posts.create",
        "posts.store",
        "posts.show",
        "posts.edit",
        "posts.update",
        "posts.destroy",
    }
    show = next(r for r in router.routes() if r.name == "posts.show")
    assert show.path == "/posts/{post}"  # singularized param


def test_api_resource_drops_form_actions() -> None:
    router = Router()
    router.api_resource("posts", PostController)
    names = {route.name for route in router.routes()}
    assert "posts.create" not in names
    assert "posts.edit" not in names
    assert {"posts.index", "posts.store", "posts.show", "posts.update", "posts.destroy"} <= names


def test_resource_only_narrows() -> None:
    router = Router()
    router.resource("posts", PostController, only=["index", "show"])
    assert {r.name for r in router.routes()} == {"posts.index", "posts.show"}


def test_resource_routes_serve() -> None:
    router = Router()
    router.resource("posts", PostController)
    kernel = HttpKernel()
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        assert client.get("/posts").json() == {"action": "index"}
        assert client.get("/posts/5").json() == {"action": "show", "id": "5"}


def test_fallback_applied_last_and_serves() -> None:
    router = Router()
    router.get("/home", lambda request: {"home": True})

    async def fb(request: Any, fallback_path: str) -> dict[str, Any]:
        return {"fallback": True, "path": fallback_path}

    router.fallback(fb)
    kernel = HttpKernel()
    router.apply_to(kernel)
    assert kernel.routes()[-1][1] == "/{fallback_path:path}"  # registered last
    with TestClient(kernel.build()) as client:
        assert client.get("/home").json() == {"home": True}
        assert client.get("/totally/missing").json()["fallback"] is True
