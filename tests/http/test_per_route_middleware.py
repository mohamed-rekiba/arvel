"""Tests for per-route middleware wiring — Story 1.

FR-025b: Route-level middleware actually executes when routes are matched.
FR-026b: Global → group → route middleware ordering (onion model) through provider.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from starlette.testclient import TestClient

from arvel.http.kernel import HttpKernel
from arvel.http.middleware import MiddlewareStack
from arvel.http.provider import _resolve_effective_middleware, _wrap_specific_route
from arvel.http.router import Router

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send


def _make_log_mw(name: str, log: list[str]):
    """Create a logging middleware class for ordering tests."""

    class _Mw:
        def __init__(self, app: ASGIApp) -> None:
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] == "http":
                log.append(f"{name}_before")
            await self.app(scope, receive, send)
            if scope["type"] == "http":
                log.append(f"{name}_after")

    _Mw.__name__ = f"_Mw_{name}"
    _Mw.__qualname__ = f"_Mw_{name}"
    return _Mw


def _build_app_with_route_mw(
    log: list[str],
    *,
    routes: list[tuple[str, str, list[str]]],
) -> FastAPI:
    """Build a FastAPI app with per-route middleware by wrapping route.app.

    Each tuple is (path, name, middleware_alias_list).
    """
    app = FastAPI()
    mw_map: dict[str, type] = {}

    for path, name, mw_names in routes:
        endpoint = _make_endpoint(name)
        app.add_api_route(path, endpoint, methods=["GET"], name=name)

        if mw_names:
            classes = []
            for mw_name in mw_names:
                if mw_name not in mw_map:
                    mw_map[mw_name] = _make_log_mw(mw_name, log)
                classes.append(mw_map[mw_name])
            _wrap_specific_route(app.routes[-1], classes)

    return app


def _make_endpoint(label: str):
    async def _ep():
        return {label: True}

    _ep.__name__ = f"ep_{label}"
    return _ep


class TestPerRouteMiddlewareWiring:
    """Route middleware declared on RouteEntry actually executes."""

    def test_route_middleware_executes_when_route_is_hit(self) -> None:
        log: list[str] = []
        app = _build_app_with_route_mw(
            log,
            routes=[
                ("/protected", "protected", ["auth"]),
            ],
        )

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/protected")

        assert response.status_code == 200
        assert "auth_before" in log
        assert "auth_after" in log

    def test_route_without_middleware_is_not_affected(self) -> None:
        log: list[str] = []
        app = _build_app_with_route_mw(
            log,
            routes=[
                ("/public", "public", []),
                ("/secret", "secret", ["auth"]),
            ],
        )

        client = TestClient(app, raise_server_exceptions=False)

        log.clear()
        client.get("/public")
        assert len(log) == 0

        log.clear()
        client.get("/secret")
        assert "auth_before" in log

    def test_group_middleware_applies_to_all_routes_in_group(self) -> None:
        log: list[str] = []
        mw_cls = _make_log_mw("group_auth", log)

        app = FastAPI()
        router = Router()

        with router.group(prefix="/api", middleware=["auth"]):
            router.get("/users", lambda: {"users": []}, name="users.index")
            router.get("/posts", lambda: {"posts": []}, name="posts.index")

        for entry in router.route_entries:
            app.add_api_route(
                entry.path,
                entry.endpoint,
                methods=sorted(entry.methods),
                name=entry.name,
            )
            if "auth" in entry.middleware:
                _wrap_specific_route(app.routes[-1], [mw_cls])

        client = TestClient(app, raise_server_exceptions=False)

        log.clear()
        client.get("/api/users")
        assert "group_auth_before" in log

        log.clear()
        client.get("/api/posts")
        assert "group_auth_before" in log

    def test_global_plus_route_middleware_ordering(self) -> None:
        log: list[str] = []
        global_mw = _make_log_mw("global", log)
        route_mw = _make_log_mw("route", log)

        app = FastAPI()

        async def handler():
            return {"ok": True}

        app.add_api_route("/items", handler, methods=["GET"], name="items")
        _wrap_specific_route(app.routes[-1], [route_mw])

        kernel = HttpKernel()
        kernel.add_global_middleware(global_mw, priority=10)
        kernel.mount(app)

        client = TestClient(app, raise_server_exceptions=False)
        client.get("/items")

        before_entries = [e for e in log if "before" in e]
        assert before_entries[0] == "global_before"
        assert "route_before" in before_entries

    def test_no_duplicate_execution_for_group_routes(self) -> None:
        log: list[str] = []
        mw_cls = _make_log_mw("auth", log)

        app = FastAPI()
        router = Router()

        with router.group(prefix="/api", middleware=["auth"]):
            router.get("/users", lambda: {"ok": True}, name="users")

        for entry in router.route_entries:
            app.add_api_route(
                entry.path,
                entry.endpoint,
                methods=sorted(entry.methods),
                name=entry.name,
            )
            if "auth" in entry.middleware:
                _wrap_specific_route(app.routes[-1], [mw_cls])

        client = TestClient(app, raise_server_exceptions=False)
        client.get("/api/users")

        auth_before_count = sum(1 for e in log if e == "auth_before")
        assert auth_before_count == 1

    def test_middleware_alias_resolved_from_stack(self) -> None:
        stack = MiddlewareStack(
            aliases={"auth": f"{__name__}._DummyMiddleware"},
        )

        resolved = stack.resolve(["auth"])
        assert len(resolved) == 1
        assert resolved[0] is _DummyMiddleware


class TestResolveEffectiveMiddleware:
    """Unit tests for the middleware resolution helper."""

    def test_empty_middleware_returns_empty(self) -> None:
        stack = MiddlewareStack(aliases={})
        result = _resolve_effective_middleware([], [], stack)
        assert result == []

    def test_exclusion_removes_middleware(self) -> None:
        stack = MiddlewareStack(
            aliases={
                "auth": f"{__name__}._DummyMiddleware",
                "csrf": f"{__name__}._DummyMiddleware2",
            },
        )
        result = _resolve_effective_middleware(["auth", "csrf"], ["csrf"], stack)
        assert len(result) == 1
        assert result[0] is _DummyMiddleware

    def test_group_expansion_in_effective_middleware(self) -> None:
        stack = MiddlewareStack(
            aliases={
                "auth": f"{__name__}._DummyMiddleware",
                "csrf": f"{__name__}._DummyMiddleware2",
            },
            groups={"web": ["csrf", "auth"]},
        )
        result = _resolve_effective_middleware(["web"], [], stack)
        assert len(result) == 2
        assert result[0] is _DummyMiddleware2
        assert result[1] is _DummyMiddleware

    def test_group_expansion_with_exclusion(self) -> None:
        stack = MiddlewareStack(
            aliases={
                "auth": f"{__name__}._DummyMiddleware",
                "csrf": f"{__name__}._DummyMiddleware2",
            },
            groups={"web": ["csrf", "auth"]},
        )
        result = _resolve_effective_middleware(["web"], ["csrf"], stack)
        assert len(result) == 1
        assert result[0] is _DummyMiddleware


class _DummyMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        await self.app(scope, receive, send)


class _DummyMiddleware2:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        await self.app(scope, receive, send)
