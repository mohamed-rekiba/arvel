"""WI-arvel-058 — ``Route.resource()`` macro for RESTful resource controllers.

Covers Epic 048 Story 3. ``Route.resource("/posts", PostController)`` should
register the seven canonical CRUD routes in one call, with conventional names
(``posts.index``, ``posts.show``, ...) and a singular path parameter for member
routes (``/posts/{post}``) so [WI-055] implicit model binding works.

The builder is fluent — ``only(...)``, ``except_(...)``, and ``names(...)``
each return the builder so calls chain.

Run BEFORE implementation — every test in this file MUST fail (Red state).
"""

from __future__ import annotations

from typing import Any

import pytest
from arvel.http.controller import Controller
from arvel.routing import Route, Router, RouteSpec
from fastapi import FastAPI
from starlette.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_router() -> None:
    Router.reset_singleton()


# ─────────────────────────── Resource controller stub ───────────────────────


class _PostController(Controller):
    """Stand-in resource controller covering all seven canonical actions."""

    async def index(self) -> dict[str, str]:
        return {"hit": "index"}

    async def create(self) -> dict[str, str]:
        return {"hit": "create"}

    async def store(self) -> dict[str, str]:
        return {"hit": "store"}

    async def show(self, post: str) -> dict[str, str]:
        return {"hit": "show", "post": post}

    async def edit(self, post: str) -> dict[str, str]:
        return {"hit": "edit", "post": post}

    async def update(self, post: str) -> dict[str, str]:
        return {"hit": "update", "post": post}

    async def destroy(self, post: str) -> dict[str, str]:
        return {"hit": "destroy", "post": post}


def _specs_by_name() -> dict[str, RouteSpec]:
    """Map every currently-registered route's name to its spec."""
    return {s.name: s for s in Router.singleton().routes() if s.name is not None}


# ─────────────────────────── Default 7-route registration ───────────────────


class TestDefaultRegistration:
    """``Route.resource()`` registers the seven canonical actions."""

    def test_registers_all_seven_routes(self) -> None:
        Route.resource("/posts", _PostController)

        specs = Router.singleton().routes()
        assert len(specs) == 7
        signatures = {(s.method, s.path) for s in specs}
        assert signatures == {
            ("GET", "/posts"),
            ("GET", "/posts/create"),
            ("POST", "/posts"),
            ("GET", "/posts/{post}"),
            ("GET", "/posts/{post}/edit"),
            ("PUT", "/posts/{post}"),
            ("DELETE", "/posts/{post}"),
        }

    def test_route_names_follow_resource_dot_action_convention(self) -> None:
        Route.resource("/posts", _PostController)

        names = {s.name for s in Router.singleton().routes() if s.name}
        assert names == {
            "posts.index",
            "posts.create",
            "posts.store",
            "posts.show",
            "posts.edit",
            "posts.update",
            "posts.destroy",
        }

    def test_each_route_binds_to_the_named_action(self) -> None:
        Route.resource("/posts", _PostController)

        specs = _specs_by_name()
        assert specs["posts.index"].controller is _PostController
        assert specs["posts.index"].action == "index"
        assert specs["posts.show"].action == "show"
        assert specs["posts.update"].action == "update"
        assert specs["posts.destroy"].action == "destroy"

    def test_routes_dispatch_through_controller_adapter(self) -> None:
        Route.resource("/posts", _PostController)

        app = FastAPI()
        Router.singleton().register_with_app(app)

        client = TestClient(app)
        assert client.get("/posts").json() == {"hit": "index"}
        assert client.get("/posts/create").json() == {"hit": "create"}
        assert client.post("/posts").json() == {"hit": "store"}
        assert client.get("/posts/42").json() == {"hit": "show", "post": "42"}
        assert client.get("/posts/42/edit").json() == {"hit": "edit", "post": "42"}
        assert client.put("/posts/42").json() == {"hit": "update", "post": "42"}
        assert client.delete("/posts/42").json() == {"hit": "destroy", "post": "42"}


# ──────────────────────────── Parameter naming ──────────────────────────────


class TestParameterNaming:
    """The member-route parameter defaults to the singular of the resource."""

    def test_default_parameter_strips_trailing_s(self) -> None:
        Route.resource("/posts", _PostController)

        show_path = next(s.path for s in Router.singleton().routes() if s.action == "show")
        assert show_path == "/posts/{post}"

    def test_default_parameter_handles_ies_plural(self) -> None:
        """``/categories`` ⇒ ``/categories/{category}``."""

        class _CategoryController(Controller):
            async def show(self, category: str) -> dict[str, str]:
                return {"hit": "show", "category": category}

        Route.resource("/categories", _CategoryController)

        show_path = next(s.path for s in Router.singleton().routes() if s.action == "show")
        assert show_path == "/categories/{category}"

    def test_explicit_parameter_override(self) -> None:
        Route.resource("/posts", _PostController, parameter="article")

        paths = {s.action: s.path for s in Router.singleton().routes()}
        assert paths["show"] == "/posts/{article}"
        assert paths["update"] == "/posts/{article}"
        assert paths["destroy"] == "/posts/{article}"


# ───────────────────────────── Filters ──────────────────────────────────────


class TestOnlyAndExcept:
    """``.only()`` / ``.except_()`` restrict the registered set."""

    def test_only_restricts_to_listed_actions(self) -> None:
        Route.resource("/posts", _PostController).only("index", "show")

        actions = {s.action for s in Router.singleton().routes()}
        assert actions == {"index", "show"}

    def test_except_excludes_listed_actions(self) -> None:
        Route.resource("/posts", _PostController).except_("create", "edit")

        actions = {s.action for s in Router.singleton().routes()}
        assert actions == {"index", "store", "show", "update", "destroy"}

    def test_only_supports_list_argument(self) -> None:
        """Either positional names or a single list/sequence works."""
        Route.resource("/posts", _PostController).only(["index", "store"])

        actions = {s.action for s in Router.singleton().routes()}
        assert actions == {"index", "store"}

    def test_except_supports_list_argument(self) -> None:
        Route.resource("/posts", _PostController).except_(["create", "edit", "destroy"])

        actions = {s.action for s in Router.singleton().routes()}
        assert actions == {"index", "store", "show", "update"}

    def test_only_rejects_unknown_action_name(self) -> None:
        with pytest.raises(ValueError, match="not a resource action"):
            Route.resource("/posts", _PostController).only("foo")


# ─────────────────────────── Name overrides ─────────────────────────────────


class TestNamesOverride:
    """``.names()`` lets the user override the generated route names."""

    def test_names_overrides_specific_actions(self) -> None:
        Route.resource("/posts", _PostController).names({"index": "posts.list"})

        names = {s.name for s in Router.singleton().routes() if s.name}
        assert "posts.list" in names
        assert "posts.index" not in names
        # Other names stay on the default convention.
        assert "posts.show" in names

    def test_names_can_override_multiple_actions(self) -> None:
        Route.resource("/posts", _PostController).names(
            {"index": "posts.list", "show": "posts.detail"}
        )

        names = {s.name for s in Router.singleton().routes() if s.name}
        assert {"posts.list", "posts.detail"}.issubset(names)
        assert "posts.index" not in names
        assert "posts.show" not in names


# ─────────────────────── Builder chains return self ─────────────────────────


class TestBuilderFluency:
    """The builder methods chain — calling order doesn't matter."""

    def test_only_and_names_chain(self) -> None:
        Route.resource("/posts", _PostController).only("index", "show").names(
            {"index": "posts.list"}
        )

        names = {s.name for s in Router.singleton().routes() if s.name}
        assert names == {"posts.list", "posts.show"}

    def test_except_and_names_chain(self) -> None:
        Route.resource("/posts", _PostController).except_("create", "edit").names(
            {"show": "posts.detail"}
        )

        names = {s.name for s in Router.singleton().routes() if s.name}
        assert "posts.detail" in names
        assert "posts.create" not in names
        assert "posts.edit" not in names


# ───────────────────── Composition: middleware + groups ─────────────────────


class TestComposition:
    """Resource registration composes with the rest of the routing pipeline."""

    def test_middleware_kwarg_attaches_to_every_route(self) -> None:
        from arvel.http.middleware import Middleware

        class _StubMw(Middleware):
            async def handle(self, request: Any, call_next: Any) -> Any:
                return await call_next(request)

        mw = _StubMw()
        Route.resource("/posts", _PostController, middleware=[mw])

        for spec in Router.singleton().routes():
            assert mw in spec.middleware

    def test_resource_inside_group_picks_up_prefix(self) -> None:
        with Route.group(prefix="/api/v1"):
            Route.resource("/posts", _PostController)

        paths = {s.path for s in Router.singleton().routes()}
        assert "/api/v1/posts" in paths
        assert "/api/v1/posts/{post}" in paths

    def test_api_shortcut_drops_create_and_edit(self) -> None:
        """``Route.api_resource()`` is the JSON-only convenience: no HTML forms."""
        Route.api_resource("/posts", _PostController)

        actions = {s.action for s in Router.singleton().routes()}
        assert actions == {"index", "store", "show", "update", "destroy"}
        assert "create" not in actions
        assert "edit" not in actions
