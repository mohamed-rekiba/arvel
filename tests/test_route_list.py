"""C8b — route:list formatter."""

from __future__ import annotations

from arvel.console.lazy import LazyGroup
from arvel.console.routes import format_routes
from arvel.routing import Router


def test_format_routes_tabulates() -> None:
    router = Router()
    router.get("/", lambda request: {}, name="home")
    router.post("/posts", lambda request: {}, name="posts.store")
    output = format_routes(router.routes())
    lines = output.splitlines()
    assert "GET" in lines[0]
    assert "/posts" in output
    assert "posts.store" in output
    assert "home" in output


def test_format_routes_empty() -> None:
    assert format_routes([]) == "(no routes registered)"


def test_route_list_in_manifest() -> None:
    assert "route:list" in LazyGroup.commands_manifest
