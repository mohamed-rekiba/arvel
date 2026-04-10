"""Tests for Middleware pipeline, aliases, and ordering — Story 2.

FR-025: Middleware alias resolution from config
FR-026: Global → group → route middleware ordering (onion model)
FR-027: Pure ASGI middleware (no BaseHTTPMiddleware)
FR-028: Middleware short-circuit (no next call → direct response)
FR-029: Terminable middleware (post-response hook)
FR-030: Global middleware priority ordering
NFR-011: Middleware pipeline overhead < 0.5ms for 3 middleware
NFR-013: Failing middleware returns 500, doesn't crash server
NFR-014: Global security middleware cannot be bypassed
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from starlette.testclient import TestClient

from arvel.http.exceptions import MiddlewareResolutionError
from arvel.http.middleware import MiddlewareStack

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send


class _FakeAuthMiddleware:
    """Module-level middleware class for alias resolution tests."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)


class TestMiddlewareProtocol:
    """FR-027: Pure ASGI middleware — not BaseHTTPMiddleware."""

    def test_middleware_is_pure_asgi(self) -> None:
        class MyMiddleware:
            def __init__(self, app: ASGIApp) -> None:
                self.app = app

            async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
                await self.app(scope, receive, send)

        assert callable(MyMiddleware)
        # Verify it doesn't inherit from BaseHTTPMiddleware
        from starlette.middleware.base import BaseHTTPMiddleware

        assert not issubclass(MyMiddleware, BaseHTTPMiddleware)


class TestMiddlewareOrdering:
    """FR-026: Global → group → route middleware ordering.
    FR-030: Priority-based global middleware ordering.
    """

    async def test_global_middleware_runs_in_priority_order(
        self, http_app_with_middleware: Any
    ) -> None:
        app, log = http_app_with_middleware
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/test")
        assert response.status_code == 200

        # Global middleware with lower priority runs first
        assert log[0] == "global_10_before"
        assert log[1] == "global_20_before"

    async def test_onion_unwind_order(self, http_app_with_middleware: Any) -> None:
        app, log = http_app_with_middleware
        client = TestClient(app, raise_server_exceptions=False)

        client.get("/test")

        before_entries = [e for e in log if "before" in e]
        after_entries = [e for e in log if "after" in e]

        # Onion: before order is A→B, after order is B→A
        assert before_entries == ["global_10_before", "global_20_before"]
        assert after_entries == ["global_20_after", "global_10_after"]

    async def test_route_middleware_runs_after_global(
        self, http_app_with_route_middleware: Any
    ) -> None:
        app, log = http_app_with_route_middleware
        client = TestClient(app, raise_server_exceptions=False)

        client.get("/protected")

        global_idx = log.index("global_before")
        route_idx = log.index("route_before")
        assert global_idx < route_idx


class TestMiddlewareShortCircuit:
    """FR-028: Middleware that doesn't call next short-circuits the pipeline."""

    async def test_short_circuit_returns_response(
        self, http_app_with_blocking_middleware: Any
    ) -> None:
        app, log = http_app_with_blocking_middleware
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/blocked")

        assert response.status_code == 403
        assert "handler" not in log


class TestTerminableMiddleware:
    """FR-029: Terminate hook fires after response is sent."""

    async def test_terminate_fires_after_response(
        self, http_app_with_terminable_middleware: Any
    ) -> None:
        app, log = http_app_with_terminable_middleware
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/test")
        assert response.status_code == 200

        # Terminate should have fired
        assert "terminate" in log


class TestMiddlewareAliases:
    """FR-025: Middleware alias resolution from config."""

    def test_resolve_known_alias(self) -> None:
        aliases = {"auth": f"{_FakeAuthMiddleware.__module__}._FakeAuthMiddleware"}
        stack = MiddlewareStack(aliases=aliases)

        resolved = stack.resolve(["auth"])
        assert len(resolved) == 1

    def test_resolve_unknown_alias_raises(self) -> None:
        stack = MiddlewareStack(aliases={})

        with pytest.raises(MiddlewareResolutionError, match="nonexistent"):
            stack.resolve(["nonexistent"])

    def test_resolve_invalid_class_path_raises(self) -> None:
        aliases = {"bad": "does.not.exist.Middleware"}
        stack = MiddlewareStack(aliases=aliases)

        with pytest.raises(MiddlewareResolutionError, match="bad"):
            stack.resolve(["bad"])


class TestMiddlewareErrorHandling:
    """NFR-013: Failing middleware returns 500, doesn't crash the ASGI server."""

    async def test_failing_middleware_returns_500(
        self, http_app_with_crashing_middleware: Any
    ) -> None:
        app = http_app_with_crashing_middleware
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/test")

        assert response.status_code == 500
        # Should be Problem Details format
        body = response.json()
        assert body.get("status") == 500


class TestGlobalMiddlewareEnforcement:
    """NFR-014: Global security middleware cannot be bypassed by route config."""

    async def test_global_middleware_always_runs(self, http_app_with_enforced_global: Any) -> None:
        app, log = http_app_with_enforced_global
        client = TestClient(app, raise_server_exceptions=False)

        client.get("/route-without-explicit-middleware")

        assert any("global_security" in entry for entry in log)
