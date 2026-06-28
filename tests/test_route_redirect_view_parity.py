"""Routing parity (Laravel): convenience routes Route::redirect / permanentRedirect / view were absent.
The redirect handlers are pure (Response with a Location header), so they're unit-tested directly; view
rendering is exercised end-to-end through the serve path (tools/e2e + the iteration's scaffold proof)."""

from __future__ import annotations

from arvel.http.response import Response
from arvel.routing import Router


async def test_redirect_route() -> None:
    router = Router()
    route = router.redirect("/old", "/new", name="old")
    assert route.methods == ["GET"]
    assert route.path == "/old"
    assert route.name == "old"
    response = await route.handler(None)
    assert isinstance(response, Response)
    assert response.status == 302
    assert response.headers["Location"] == "/new"


async def test_permanent_redirect_route() -> None:
    router = Router()
    route = router.permanent_redirect("/ancient", "/home")
    response = await route.handler(None)
    assert response.status == 301
    assert response.headers["Location"] == "/home"


def test_view_route_is_registered() -> None:
    router = Router()
    route = router.view("/about", "pages.about", {"title": "About"}, name="about")
    assert route.methods == ["GET"]
    assert route.path == "/about"
    assert route.name == "about"
    assert callable(route.handler)


def test_redirect_respects_group_prefix() -> None:
    router = Router()
    with router.group(prefix="/admin", name="admin."):
        route = router.redirect("/dashboard", "/admin/home", name="dash")
    assert route.path == "/admin/dashboard"
    assert route.name == "admin.dash"
