"""FR-002-004 — RouteServiceProvider ABC."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_route_service_provider_is_abstract() -> None:
    from arvel.routing import RouteServiceProvider

    assert inspect_abstract(RouteServiceProvider, "map_routes")


def test_subclass_without_map_routes_cannot_instantiate() -> None:
    from arvel.application import Application
    from arvel.routing import RouteServiceProvider

    app = Application()

    class Incomplete(RouteServiceProvider):
        pass

    cls: type = Incomplete
    with pytest.raises(TypeError):
        cls(app)


@pytest.mark.asyncio
async def test_map_routes_is_called_during_boot(tmp_path: Path) -> None:
    from arvel import Application
    from arvel.providers import HttpServiceProvider
    from arvel.routing import Router, RouteServiceProvider

    Router.reset_singleton()
    map_called = False

    class MyRoutes(RouteServiceProvider):
        def map_routes(self, router: Router) -> None:
            nonlocal map_called
            map_called = True
            assert isinstance(router, Router)

    app = (
        Application.configure(tmp_path)
        .with_environment("local")
        .with_providers([HttpServiceProvider, MyRoutes])
        .create()
    )
    await app.boot()
    assert map_called


def inspect_abstract(cls: type, method: str) -> bool:
    """Helper: is method abstract on cls?"""
    method_obj = getattr(cls, method, None)
    return getattr(method_obj, "__isabstractmethod__", False) is True
