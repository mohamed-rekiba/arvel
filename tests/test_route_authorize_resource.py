"""Routing — ``Controller.authorize_resource(Model)`` auto-maps RESTful actions to policy
abilities (index→viewAny, show→view, store→create, update→update, destroy→delete), spec 15 §109.
Test-first."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.auth import AuthorizationError, Gate
from arvel.kernel import Application, set_application
from arvel.routing import Controller, Router


class Post:
    __name__ = "Post"


@pytest.fixture
def gate_app() -> Any:
    gate = Gate()
    app = Application()
    app.instance("gate", gate)
    set_application(app)
    try:
        yield gate
    finally:
        set_application(None)


def _route(router: Router, name: str) -> Any:
    return next(r for r in router._routes if r.name == name)


class PostController(Controller):
    async def index(self, **kwargs: Any) -> str:
        return "listed"

    async def show(self, **kwargs: Any) -> str:
        return "shown"


PostController.authorize_resource(Post)


async def test_index_maps_to_view_any_and_blocks_when_denied(gate_app: Gate) -> None:
    gate_app.define("viewAny", lambda user, *a: False)
    router = Router().resource("posts", PostController)
    handler = _route(router, "posts.index").handler
    with pytest.raises(AuthorizationError):
        await handler()


async def test_index_allows_when_permitted(gate_app: Gate) -> None:
    gate_app.define("viewAny", lambda user, *a: True)
    router = Router().resource("posts", PostController)
    handler = _route(router, "posts.index").handler
    assert await handler() == "listed"


async def test_show_maps_to_view_against_bound_instance(gate_app: Gate) -> None:
    seen: dict[str, Any] = {}

    def check(user: Any, target: Any) -> bool:
        seen["target"] = target
        return False

    gate_app.define("view", check)
    router = Router().resource("posts", PostController)
    handler = _route(router, "posts.show").handler
    instance = Post()
    with pytest.raises(AuthorizationError):
        await handler(post=instance)
    assert seen["target"] is instance  # authorized against the bound model instance


async def test_no_authorization_without_declaration(gate_app: Gate) -> None:
    class Open(Controller):
        async def index(self, **kwargs: Any) -> str:
            return "ok"

    router = Router().resource("open", Open)
    handler = _route(router, "open.index").handler
    assert await handler() == "ok"  # no policy declared → no gate check
