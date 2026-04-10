"""Tests for HttpKernel — middleware stack orchestration.

FR-026: Global middleware execution order
FR-030: Priority-based global middleware
NFR-018: Middleware registration logged at boot
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from arvel.http.kernel import HttpKernel

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send


class TestHttpKernel:
    """HttpKernel orchestrates the global middleware stack."""

    def test_add_global_middleware(self) -> None:
        class DummyMiddleware:
            def __init__(self, app: ASGIApp) -> None:
                self.app = app

            async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
                await self.app(scope, receive, send)

        kernel = HttpKernel()
        kernel.add_global_middleware(DummyMiddleware, priority=10)

        assert len(kernel.global_middleware) == 1

    def test_middleware_sorted_by_priority(self) -> None:
        class MwA:
            def __init__(self, app: ASGIApp) -> None:
                self.app = app

            async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
                await self.app(scope, receive, send)

        class MwB:
            def __init__(self, app: ASGIApp) -> None:
                self.app = app

            async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
                await self.app(scope, receive, send)

        kernel = HttpKernel()
        kernel.add_global_middleware(MwB, priority=20)
        kernel.add_global_middleware(MwA, priority=10)

        sorted_mw = kernel.sorted_middleware()
        assert sorted_mw[0][0] is MwA
        assert sorted_mw[1][0] is MwB

    def test_duplicate_middleware_class_raises(self) -> None:
        class MwA:
            def __init__(self, app: ASGIApp) -> None:
                self.app = app

            async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
                await self.app(scope, receive, send)

        kernel = HttpKernel()
        kernel.add_global_middleware(MwA, priority=10)

        with pytest.raises(ValueError, match="already registered"):
            kernel.add_global_middleware(MwA, priority=20)
