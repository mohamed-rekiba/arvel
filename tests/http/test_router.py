"""Tests for Router and route discovery — Story 1.

FR-021: Module routes.py auto-discovery
FR-022: Route registration with method, path, handler, name
FR-023: Route groups with prefix, middleware, name prefix
FR-024: Module discovery ordering (alphabetical, provider priority override)
FR-036: Duplicate route name raises at boot
FR-037: Route summary logged at boot
NFR-012: Route matching latency < 0.2ms for 100 routes
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from arvel.http.exceptions import RouteRegistrationError
from arvel.http.router import Router, discover_routes

if TYPE_CHECKING:
    from pathlib import Path

    pass


class TestRouteRegistration:
    """FR-022: Route registration with method, path, handler, and name."""

    def test_register_get_route(self) -> None:
        router = Router()

        async def handler() -> dict:
            return {"ok": True}

        router.get("/items", handler, name="items.index")

        routes = router.route_entries
        assert len(routes) == 1
        assert routes[0].path == "/items"
        assert routes[0].name == "items.index"
        assert routes[0].methods == {"GET"}

    def test_register_post_route(self) -> None:
        router = Router()

        async def handler() -> dict:
            return {"created": True}

        router.post("/items", handler, name="items.store")

        routes = router.route_entries
        assert len(routes) == 1
        assert routes[0].methods == {"POST"}

    def test_register_put_route(self) -> None:
        router = Router()

        async def handler() -> dict:
            return {"updated": True}

        router.put("/items/{id}", handler, name="items.update")

        routes = router.route_entries
        assert routes[0].methods == {"PUT"}

    def test_register_patch_route(self) -> None:
        router = Router()

        async def handler() -> dict:
            return {"patched": True}

        router.patch("/items/{id}", handler, name="items.patch")

        routes = router.route_entries
        assert routes[0].methods == {"PATCH"}

    def test_register_delete_route(self) -> None:
        router = Router()

        async def handler() -> dict:
            return {"deleted": True}

        router.delete("/items/{id}", handler, name="items.destroy")

        routes = router.route_entries
        assert routes[0].methods == {"DELETE"}

    def test_register_route_without_name(self) -> None:
        router = Router()

        async def handler() -> dict:
            return {}

        router.get("/health", handler)

        routes = router.route_entries
        assert len(routes) == 1
        assert routes[0].name is None or routes[0].name == ""

    def test_route_with_middleware_list(self) -> None:
        router = Router()

        async def handler() -> dict:
            return {}

        router.get("/secret", handler, name="secret", middleware=["auth"])

        routes = router.route_entries
        assert routes[0].middleware == ["auth"]


class TestRouteGroup:
    """FR-023: Route groups with prefix, middleware, name prefix."""

    def test_group_applies_prefix(self) -> None:
        router = Router()

        async def handler() -> dict:
            return {}

        with router.group(prefix="/api/v1") as r:
            r.get("/users", handler, name="users.index")

        routes = router.route_entries
        assert routes[0].path == "/api/v1/users"

    def test_group_applies_middleware(self) -> None:
        router = Router()

        async def handler() -> dict:
            return {}

        with router.group(middleware=["auth"]) as r:
            r.get("/users", handler, name="users.index")

        routes = router.route_entries
        assert "auth" in routes[0].middleware

    def test_group_applies_name_prefix(self) -> None:
        router = Router()

        async def handler() -> dict:
            return {}

        with router.group(name="api.") as r:
            r.get("/users", handler, name="users.index")

        routes = router.route_entries
        assert routes[0].name == "api.users.index"

    def test_nested_groups(self) -> None:
        router = Router()

        async def handler() -> dict:
            return {}

        with (
            router.group(prefix="/api", middleware=["cors"], name="api.") as outer,
            outer.group(prefix="/v1", middleware=["auth"], name="v1.") as inner,
        ):
            inner.get("/users", handler, name="users.index")

        routes = router.route_entries
        assert routes[0].path == "/api/v1/users"
        assert routes[0].name == "api.v1.users.index"
        assert "cors" in routes[0].middleware
        assert "auth" in routes[0].middleware

    def test_group_with_empty_prefix(self) -> None:
        router = Router()

        async def handler() -> dict:
            return {}

        with router.group(middleware=["log"]) as r:
            r.get("/items", handler, name="items.index")

        routes = router.route_entries
        assert routes[0].path == "/items"
        assert "log" in routes[0].middleware

    def test_group_accepts_keyword_arguments(self) -> None:
        router = Router()

        async def handler() -> dict:
            return {}

        with router.group(prefix="/api", middleware=["auth"], name="api.") as r:
            r.get("/users", handler, name="users.index")

        route = router.route_entries[0]
        assert route.path == "/api/users"
        assert route.name == "api.users.index"
        assert "auth" in route.middleware

    def test_group_allows_empty_arguments(self) -> None:
        router = Router()
        with router.group() as r:
            r.get("/health", lambda: {"ok": True}, name="health")
        assert router.route_entries[0].path == "/health"


class TestDuplicateRouteNames:
    """FR-036: Duplicate route names raise at boot."""

    def test_duplicate_name_raises_error(self) -> None:
        router = Router()

        async def handler_a() -> dict:
            return {}

        async def handler_b() -> dict:
            return {}

        router.get("/a", handler_a, name="items.index")

        with pytest.raises(RouteRegistrationError, match=r"items\.index"):
            router.get("/b", handler_b, name="items.index")


class TestRouteDiscovery:
    """FR-021: ``routes/*.py`` auto-discovery.
    FR-024: Discovery order is alphabetical by route file stem.
    """

    def test_discover_routes_from_modules(self, tmp_project: Path) -> None:
        routes_dir = tmp_project / "routes"
        routes_dir.mkdir(parents=True)
        (routes_dir / "users.py").write_text(
            "from arvel.http.router import Router\n\n"
            "router = Router()\n\n"
            "@router.get('/users', name='users.index')\n"
            "async def list_users():\n"
            "    return []\n"
        )

        routers = discover_routes(tmp_project)
        assert len(routers) == 1

    def test_discover_multiple_modules_alphabetical(self, tmp_project: Path) -> None:
        routes_dir = tmp_project / "routes"
        routes_dir.mkdir(parents=True)
        for name in ("billing", "auth"):
            (routes_dir / f"{name}.py").write_text(
                "from arvel.http.router import Router\n\n"
                f"router = Router()\n"
                f"router.get('/{name}', lambda: {{}}, name='{name}.index')\n"
            )

        routers = discover_routes(tmp_project)
        assert len(routers) == 2
        # auth comes before billing alphabetically
        assert routers[0][0] == "auth"
        assert routers[1][0] == "billing"

    def test_discover_skips_module_without_routes_py(self, tmp_project: Path) -> None:
        routes_dir = tmp_project / "routes"
        routes_dir.mkdir(parents=True)
        # No .py route files

        routers = discover_routes(tmp_project)
        assert len(routers) == 0

    def test_discover_skips_module_without_router_export(self, tmp_project: Path) -> None:
        routes_dir = tmp_project / "routes"
        routes_dir.mkdir(parents=True)
        (routes_dir / "users.py").write_text("# No router export\nx = 42\n")

        routers = discover_routes(tmp_project)
        assert len(routers) == 0
