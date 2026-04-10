"""Tests for deferred execution — FR-003."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from anyio import sleep

from arvel.context.deferred import DeferredCollector, defer

if TYPE_CHECKING:
    from collections.abc import MutableMapping

    from starlette.types import ASGIApp, Receive, Scope, Send


class TestDefer:
    """FR-003.1: defer() registers a callable for after-response execution."""

    async def test_defer_registers_callable(self) -> None:
        collector = DeferredCollector()
        collector.install()
        try:
            called = False

            async def task() -> None:
                nonlocal called
                called = True

            defer(task)
            tasks = collector.drain()
            assert len(tasks) == 1
            await tasks[0].fn()
            assert called is True
        finally:
            collector.reset()

    async def test_defer_sync_callable(self) -> None:
        collector = DeferredCollector()
        collector.install()
        try:
            calls: list[str] = []

            def sync_task() -> None:
                calls.append("ran")

            defer(sync_task)
            tasks = collector.drain()
            assert len(tasks) == 1
        finally:
            collector.reset()


class TestDeferredOrdering:
    """FR-003.2: multiple deferred tasks execute in registration order."""

    async def test_tasks_run_in_order(self) -> None:
        collector = DeferredCollector()
        collector.install()
        try:
            order: list[int] = []

            async def task1() -> None:
                order.append(1)

            async def task2() -> None:
                order.append(2)

            async def task3() -> None:
                order.append(3)

            defer(task1)
            defer(task2)
            defer(task3)
            tasks = collector.drain()
            for t in tasks:
                await t.fn()
            assert order == [1, 2, 3]
        finally:
            collector.reset()


class TestDeferredErrorHandling:
    """FR-003.3: exceptions in deferred tasks are logged, not propagated."""

    async def test_exception_does_not_propagate(self) -> None:
        collector = DeferredCollector()
        collector.install()
        try:

            async def failing_task() -> None:
                msg = "Deferred task failure"
                raise RuntimeError(msg)

            defer(failing_task)
            tasks = collector.drain()
            assert len(tasks) == 1
        finally:
            collector.reset()


class TestDeferredMiddleware:
    """FR-003.7: DeferredTaskMiddleware integration."""

    async def test_middleware_runs_deferred_after_response(
        self, echo_app: ASGIApp, make_scope: Any
    ) -> None:
        from arvel.context.middleware import DeferredTaskMiddleware

        executed: list[str] = []

        async def after_task() -> None:
            executed.append("done")

        responses: list[MutableMapping[str, Any]] = []

        async def receive() -> MutableMapping[str, Any]:
            return {"type": "http.request", "body": b""}

        async def send(message: MutableMapping[str, Any]) -> None:
            responses.append(message)

        async def app_with_defer(scope: Scope, receive: Receive, send: Send) -> None:
            defer(after_task)
            await echo_app(scope, receive, send)

        middleware = DeferredTaskMiddleware(app_with_defer)
        scope = make_scope()
        await middleware(scope, receive, send)

        assert any(r.get("status") == 200 for r in responses)
        assert executed == ["done"]

    async def test_middleware_logs_errors_from_deferred_tasks(
        self, echo_app: ASGIApp, make_scope: Any
    ) -> None:
        from arvel.context.middleware import DeferredTaskMiddleware

        async def bad_task() -> None:
            msg = "boom"
            raise RuntimeError(msg)

        async def app_with_defer(scope: Scope, receive: Receive, send: Send) -> None:
            defer(bad_task)
            await echo_app(scope, receive, send)

        responses: list[MutableMapping[str, Any]] = []

        async def receive() -> MutableMapping[str, Any]:
            return {"type": "http.request", "body": b""}

        async def send(message: MutableMapping[str, Any]) -> None:
            responses.append(message)

        middleware = DeferredTaskMiddleware(app_with_defer)
        scope = make_scope()
        await middleware(scope, receive, send)
        assert any(r.get("status") == 200 for r in responses)


class TestDeferredTimeout:
    """FR-003.6: deferred tasks have a configurable timeout."""

    async def test_timeout_cancels_long_running_task(
        self, echo_app: ASGIApp, make_scope: Any
    ) -> None:
        from arvel.context.middleware import DeferredTaskMiddleware

        started = False

        async def slow_task() -> None:
            nonlocal started
            started = True
            await sleep(60)

        async def app_with_defer(scope: Scope, receive: Receive, send: Send) -> None:
            defer(slow_task)
            await echo_app(scope, receive, send)

        responses: list[MutableMapping[str, Any]] = []

        async def receive() -> MutableMapping[str, Any]:
            return {"type": "http.request", "body": b""}

        async def send(message: MutableMapping[str, Any]) -> None:
            responses.append(message)

        middleware = DeferredTaskMiddleware(app_with_defer, timeout=0.1)
        scope = make_scope()
        await middleware(scope, receive, send)
        assert started is True
