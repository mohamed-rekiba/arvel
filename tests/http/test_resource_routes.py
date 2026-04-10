"""Tests for resource route registration — Story 2.

FR-040: router.resource() auto-registers CRUD routes
FR-042: only= and except_= filtering
FR-043: Resource routes inherit group prefix and middleware
FR-044: Resource routes get conventional names
"""

from __future__ import annotations

import pytest

from arvel.http.exceptions import RouteRegistrationError
from arvel.http.router import Router


class _PhotoController:
    """Fake controller with all CRUD methods."""

    @staticmethod
    async def index():
        return {"photos": []}

    @staticmethod
    async def store():
        return {"created": True}

    @staticmethod
    async def show(id: int):  # noqa: A002
        return {"id": id}

    @staticmethod
    async def update(id: int):  # noqa: A002
        return {"updated": id}

    @staticmethod
    async def destroy(id: int):  # noqa: A002
        return {"deleted": id}


class _PartialController:
    """Controller missing some CRUD methods."""

    @staticmethod
    async def index():
        return {"items": []}

    @staticmethod
    async def show(id: int):  # noqa: A002
        return {"id": id}


class TestResourceRegistration:
    """FR-040: Resource route registration."""

    def test_resource_registers_all_crud_routes(self) -> None:
        router = Router()
        router.resource("photos", _PhotoController)

        routes = router.route_entries
        assert len(routes) == 5

        paths_methods = {(r.path, frozenset(r.methods)) for r in routes}
        assert ("/photos", frozenset({"GET"})) in paths_methods
        assert ("/photos", frozenset({"POST"})) in paths_methods
        assert ("/photos/{id}", frozenset({"GET"})) in paths_methods
        assert ("/photos/{id}", frozenset({"PUT"})) in paths_methods
        assert ("/photos/{id}", frozenset({"DELETE"})) in paths_methods

    def test_resource_routes_have_conventional_names(self) -> None:
        router = Router()
        router.resource("photos", _PhotoController)

        names = {r.name for r in router.route_entries}
        assert names == {
            "photos.index",
            "photos.store",
            "photos.show",
            "photos.update",
            "photos.destroy",
        }

    def test_resource_with_only_filter(self) -> None:
        router = Router()
        router.resource("photos", _PhotoController, only=["index", "show"])

        routes = router.route_entries
        assert len(routes) == 2
        names = {r.name for r in routes}
        assert names == {"photos.index", "photos.show"}

    def test_resource_with_except_filter(self) -> None:
        router = Router()
        router.resource("photos", _PhotoController, except_=["destroy"])

        routes = router.route_entries
        assert len(routes) == 4
        names = {r.name for r in routes}
        assert "photos.destroy" not in names
        assert "photos.index" in names
        assert "photos.store" in names
        assert "photos.show" in names
        assert "photos.update" in names

    def test_resource_missing_controller_method_raises(self) -> None:
        router = Router()
        with pytest.raises(RouteRegistrationError, match="missing method 'store'"):
            router.resource("items", _PartialController)

    def test_resource_with_only_skips_missing_methods(self) -> None:
        router = Router()
        router.resource("items", _PartialController, only=["index", "show"])

        routes = router.route_entries
        assert len(routes) == 2


class TestResourceInGroups:
    """FR-043: Resource routes inherit group prefix and middleware."""

    def test_resource_inside_group_inherits_prefix(self) -> None:
        router = Router()
        with router.group(prefix="/api/v1"):
            router.resource("photos", _PhotoController)

        paths = [r.path for r in router.route_entries]
        assert all(p.startswith("/api/v1/photos") for p in paths)

    def test_resource_inside_group_inherits_middleware(self) -> None:
        router = Router()
        with router.group(middleware=["auth"]):
            router.resource("photos", _PhotoController)

        for route in router.route_entries:
            assert "auth" in route.middleware

    def test_resource_inside_named_group(self) -> None:
        router = Router()
        with router.group(prefix="/api", name="api."):
            router.resource("photos", _PhotoController)

        names = {r.name for r in router.route_entries if r.name is not None}
        assert names
        assert all(n.startswith("api.photos.") for n in names)

    def test_resource_with_extra_middleware(self) -> None:
        router = Router()
        router.resource("photos", _PhotoController, middleware=["throttle"])

        for route in router.route_entries:
            assert "throttle" in route.middleware
