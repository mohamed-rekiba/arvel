"""Tests for terminable middleware protocol — Story 6.

FR-057: TerminableMiddleware protocol with terminate() hook
FR-058: terminate() called after response is sent
FR-059: terminate() exception doesn't affect the response
FR-060: Multiple terminable middleware terminate in reverse order
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI
from starlette.testclient import TestClient

from arvel.http.kernel import HttpKernel
from arvel.http.middleware import TerminableMiddleware

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send


def _make_terminable_mw(name: str, log: list[str]):
    """Create a terminable middleware that logs before/after/terminate."""

    class _TMw:
        def __init__(self, app: ASGIApp) -> None:
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] == "http":
                log.append(f"{name}_before")
            await self.app(scope, receive, send)
            if scope["type"] == "http":
                log.append(f"{name}_after")
                await self.terminate()

        async def terminate(self) -> None:
            log.append(f"{name}_terminate")

    _TMw.__name__ = f"_TMw_{name}"
    _TMw.__qualname__ = f"_TMw_{name}"
    return _TMw


def _make_crashing_terminable_mw(name: str, log: list[str]):
    """Terminable middleware whose terminate() raises."""

    class _CrashTMw:
        def __init__(self, app: ASGIApp) -> None:
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            await self.app(scope, receive, send)
            if scope["type"] == "http":
                try:
                    await self.terminate()
                except RuntimeError:
                    log.append(f"{name}_terminate_error")

        async def terminate(self) -> None:
            raise RuntimeError("terminate crash")

    _CrashTMw.__name__ = f"_CrashTMw_{name}"
    _CrashTMw.__qualname__ = f"_CrashTMw_{name}"
    return _CrashTMw


class TestTerminableMiddlewareProtocol:
    """FR-057: TerminableMiddleware protocol."""

    def test_terminable_protocol_check(self) -> None:
        log: list[str] = []
        cls = _make_terminable_mw("test", log)

        class _App:
            pass

        instance = cls(_App())
        assert isinstance(instance, TerminableMiddleware)

    def test_non_terminable_middleware_is_not_matched(self) -> None:
        class _RegularMw:
            def __init__(self, app):
                self.app = app

            async def __call__(self, scope, receive, send):
                await self.app(scope, receive, send)

        class _App:
            pass

        instance = _RegularMw(_App())
        assert not isinstance(instance, TerminableMiddleware)


class TestTerminableExecution:
    """FR-058: terminate() fires after response."""

    def test_terminate_fires_after_response(self) -> None:
        log: list[str] = []
        mw = _make_terminable_mw("mw", log)

        app = FastAPI()

        @app.get("/test")
        async def handler():
            return {"ok": True}

        kernel = HttpKernel()
        kernel.add_global_middleware(mw, priority=10)
        kernel.mount(app)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test")

        assert response.status_code == 200
        assert "mw_terminate" in log
        assert log.index("mw_before") < log.index("mw_terminate")

    def test_terminate_exception_does_not_affect_response(self) -> None:
        log: list[str] = []
        mw = _make_crashing_terminable_mw("crash", log)

        app = FastAPI()

        @app.get("/test")
        async def handler():
            return {"ok": True}

        kernel = HttpKernel()
        kernel.add_global_middleware(mw, priority=10)
        kernel.mount(app)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test")

        assert response.status_code == 200
        assert "crash_terminate_error" in log


class TestMultipleTerminableMiddleware:
    """FR-060: Multiple terminable middleware terminate in reverse order."""

    def test_reverse_terminate_order(self) -> None:
        log: list[str] = []
        mw_a = _make_terminable_mw("a", log)
        mw_b = _make_terminable_mw("b", log)

        app = FastAPI()

        @app.get("/test")
        async def handler():
            return {"ok": True}

        kernel = HttpKernel()
        kernel.add_global_middleware(mw_a, priority=10)
        kernel.add_global_middleware(mw_b, priority=20)
        kernel.mount(app)

        client = TestClient(app, raise_server_exceptions=False)
        client.get("/test")

        terminate_entries = [e for e in log if "terminate" in e]
        # Onion: a wraps b, so b terminates first (inner → outer)
        assert terminate_entries[0] == "b_terminate"
        assert terminate_entries[1] == "a_terminate"
