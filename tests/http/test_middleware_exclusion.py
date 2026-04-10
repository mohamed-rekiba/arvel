"""Tests for middleware exclusion (without_middleware) — Story 5.

FR-054: without_middleware removes specific middleware from a route
FR-055: Exclusion on routes outside groups removes global middleware
FR-056: Excluding non-existent middleware is a no-op
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.http.middleware import MiddlewareStack
from arvel.http.router import Router

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send


class _StubA:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)


class _StubB:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)


class TestWithoutMiddleware:
    """FR-054: Route-level middleware exclusion."""

    def test_without_middleware_recorded_on_route_entry(self) -> None:
        router = Router()

        async def handler():
            return {}

        with router.group(middleware=["csrf", "auth"]):
            router.get(
                "/webhook",
                handler,
                name="webhook",
                without_middleware=["csrf"],
            )

        route = router.route_entries[0]
        assert "csrf" in route.without_middleware
        assert "auth" not in route.without_middleware

    def test_exclusion_removes_middleware_from_effective_stack(self) -> None:
        stack = MiddlewareStack(
            aliases={
                "csrf": f"{__name__}._StubA",
                "auth": f"{__name__}._StubB",
            },
        )

        middleware_names = ["csrf", "auth"]
        exclude_names = ["csrf"]

        expanded = stack.expand(middleware_names)
        exclude_expanded = set(stack.expand(exclude_names))
        effective = [n for n in expanded if n not in exclude_expanded]

        assert effective == ["auth"]

    def test_exclusion_on_route_outside_group(self) -> None:
        router = Router()

        async def handler():
            return {}

        router.get(
            "/public",
            handler,
            name="public",
            middleware=["csrf", "auth"],
            without_middleware=["csrf"],
        )

        route = router.route_entries[0]
        assert "csrf" in route.middleware
        assert "csrf" in route.without_middleware

    def test_excluding_nonexistent_middleware_is_noop(self) -> None:
        stack = MiddlewareStack(
            aliases={"auth": f"{__name__}._StubB"},
        )

        middleware_names = ["auth"]
        exclude_names = ["nonexistent"]

        expanded = stack.expand(middleware_names)
        exclude_expanded = set(stack.expand(exclude_names))
        effective = [n for n in expanded if n not in exclude_expanded]

        assert effective == ["auth"]

    def test_exclusion_works_with_groups(self) -> None:
        stack = MiddlewareStack(
            aliases={
                "csrf": f"{__name__}._StubA",
                "auth": f"{__name__}._StubB",
            },
            groups={"web": ["csrf", "auth"]},
        )

        expanded = stack.expand(["web"])
        exclude_expanded = set(stack.expand(["csrf"]))
        effective = [n for n in expanded if n not in exclude_expanded]

        assert effective == ["auth"]


class TestWithoutMiddlewareLogging:
    """FR-055: Exclusion is explicit and auditable."""

    def test_excluded_middleware_visible_on_route_entry(self) -> None:
        router = Router()

        async def handler():
            return {}

        with router.group(middleware=["csrf", "auth", "log"]):
            router.get(
                "/webhook",
                handler,
                name="webhook",
                without_middleware=["csrf", "log"],
            )

        route = router.route_entries[0]
        assert set(route.without_middleware) == {"csrf", "log"}
        assert set(route.middleware) == {"csrf", "auth", "log"}
