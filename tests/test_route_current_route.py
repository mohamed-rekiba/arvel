"""H4 — the current-route accessor: inside a handler, ``url().current_route()`` (and the
identical ``Router.current_route()`` surface a bound ``Route`` facade reads) exposes the matched
route's name + resolved params; ``current_route_named(pattern)`` is an fnmatch convenience.
Outside a request it degrades to ``None``/``False`` rather than raising — unlike ``url().current()``,
"no current route" is a legitimate state (no active request at all)."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.routing import Router, url


async def _show(request: Any, item: str) -> dict[str, Any]:
    match = url().current_route()
    assert match is not None
    return {
        "name": match.name,
        "params": match.params,
        "named": url().current_route_named("shop.*"),
    }


def _client(router: Router) -> TestClient[Any]:
    kernel = HttpKernel()
    router.apply_to(kernel)
    return TestClient(kernel.build())


def test_current_route_readable_inside_handler() -> None:
    router = Router()
    router.get("/items/{item}", _show, name="shop.show")
    with _client(router) as client:
        response = client.get("/items/42")
        assert response.json() == {
            "name": "shop.show",
            "params": {"item": "42"},
            "named": True,
        }


def test_current_route_named_false_for_non_matching_pattern() -> None:
    async def handler(request: Any) -> dict[str, Any]:
        return {"named": url().current_route_named("admin.*")}

    router = Router()
    router.get("/x", handler, name="shop.x")
    with _client(router) as client:
        assert client.get("/x").json() == {"named": False}


def test_current_route_none_outside_a_request() -> None:
    assert url().current_route() is None
    assert url().current_route_named("anything") is False


def test_router_current_route_matches_url_generator() -> None:
    async def handler(request: Any) -> dict[str, Any]:
        router_match = router.current_route()
        assert router_match is not None
        return {"name": router_match.name}

    router = Router()
    router.get("/r", handler, name="named.route")
    with _client(router) as client:
        assert client.get("/r").json() == {"name": "named.route"}


def test_fallback_route_reflects_as_current_route() -> None:
    async def fallback_handler(request: Any, fallback_path: str) -> dict[str, Any]:
        match = url().current_route()
        assert match is not None
        return {"name": match.name}

    router = Router()
    router.fallback(fallback_handler)
    with _client(router) as client:
        assert client.get("/nope/nowhere").json() == {"name": "fallback"}
