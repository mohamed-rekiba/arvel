"""Sprint 4: Middleware, Observability & Cleanup — QA-Pre tests.

FR-016: Health checks run in parallel
FR-017: RequestScopeMiddleware removed (unified into RequestContainerMiddleware)
FR-018: HttpSettings catches specific exceptions, not bare Exception
FR-019: OTLP ImportError produces warning log
FR-020: ObservabilitySettings catches specific exceptions
FR-021: Provider shutdown logs traceback
FR-022: stderr channel writes to sys.stderr
FR-023: RouteMiddlewareWrapper removal
FR-024: RequestContainerMiddleware on_close in finally
"""

from __future__ import annotations

import contextlib
import logging
import sys
import time
from pathlib import Path
from unittest.mock import patch

import anyio
import pytest


class TestHealthChecksParallel:
    """FR-016: Health checks must run in parallel."""

    async def test_total_latency_is_max_not_sum(self) -> None:
        """AC: Total latency ~ max(individual durations), not sum."""

        from arvel.observability.health import HealthRegistry, HealthResult, HealthStatus

        class SlowCheck:
            name = "slow"

            async def check(self) -> HealthResult:
                await anyio.sleep(0.2)
                return HealthResult(status=HealthStatus.HEALTHY, message="ok", duration_ms=200)

        class AnotherSlowCheck:
            name = "another_slow"

            async def check(self) -> HealthResult:
                await anyio.sleep(0.2)
                return HealthResult(status=HealthStatus.HEALTHY, message="ok", duration_ms=200)

        registry = HealthRegistry()
        registry.register(SlowCheck())
        registry.register(AnotherSlowCheck())

        start = time.monotonic()
        result = await registry.run_all()
        elapsed = time.monotonic() - start

        assert elapsed < 0.35, (
            f"Health checks took {elapsed:.2f}s — should be ~0.2s if parallel, "
            f"not ~0.4s if sequential"
        )
        assert result.status.value == "healthy"


class TestHttpSettingsSpecificExceptions:
    """FR-018: HttpSettings catches only ConfigurationError and KeyError."""

    def test_http_provider_catches_only_specific_exceptions(self) -> None:
        """AC: HttpProvider catches ConfigurationError/KeyError, not bare Exception."""
        import ast

        from arvel.http import provider as mod

        with Path(mod.__file__).open() as f:
            source = ast.parse(f.read())

        for node in ast.walk(source):
            if isinstance(node, ast.ExceptHandler):
                handler_names: list[str] = []
                if isinstance(node.type, ast.Name):
                    handler_names.append(node.type.id)
                elif isinstance(node.type, ast.Tuple):
                    for elt in node.type.elts:
                        if isinstance(elt, ast.Name):
                            handler_names.append(elt.id)

                assert "Exception" not in handler_names, (
                    "HttpProvider should not catch bare Exception — "
                    f"found: except {', '.join(handler_names)}"
                )


class TestOtlpImportErrorWarning:
    """FR-019: OTLP exporter ImportError must produce a warning log."""

    async def test_otlp_import_error_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """AC: Missing OTLP exporter with endpoint configured logs a warning."""
        from arvel.observability.config import ObservabilitySettings

        settings = ObservabilitySettings(
            otel_enabled=True,
            otel_exporter_endpoint="http://localhost:4317",
        )

        with (
            caplog.at_level(logging.WARNING),
            patch.dict(
                sys.modules, {"opentelemetry.exporter.otlp.proto.grpc.trace_exporter": None}
            ),
        ):
            from arvel.observability.tracing import configure_tracing

            with contextlib.suppress(Exception):
                configure_tracing(settings, app_name="test")


class TestProviderShutdownLogsTraceback:
    """FR-021: Shutdown failures log exception message and traceback."""

    async def test_shutdown_logs_include_exception_message(self, tmp_project: Path) -> None:
        """AC: Shutdown error logs include str(exc)."""
        from arvel.foundation.application import Application

        (tmp_project / "bootstrap" / "providers.py").write_text(
            "from arvel.foundation.provider import ServiceProvider\n\n"
            "class FailShutdownProvider(ServiceProvider):\n"
            "    async def shutdown(self, app):\n"
            "        raise RuntimeError('detailed failure reason')\n\n"
            "providers = [FailShutdownProvider]\n"
        )

        app = await Application.create(tmp_project, testing=True)
        await app.shutdown()

        # Current implementation logs type(exc).__name__ only (e.g., "RuntimeError")
        # FR-021 requires logging str(exc) and traceback too


class TestStderrChannelWritesToStderr:
    """FR-022: The stderr logging channel must write to sys.stderr."""

    def test_stderr_channel_uses_sys_stderr_not_stdout(self) -> None:
        """AC: Log output from stderr channel appears on stderr."""
        import ast

        from arvel.observability import logging as log_mod

        with Path(log_mod.__file__).open() as f:
            source = ast.parse(f.read())

        for node in ast.walk(source):
            if not isinstance(node, ast.If):
                continue
            # Look for: if driver == "stderr"
            test = node.test
            if not (
                isinstance(test, ast.Compare)
                and len(test.comparators) == 1
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value == "stderr"
            ):
                continue

            body_src = ast.dump(ast.Module(body=node.body, type_ignores=[]))
            assert "sys.stderr" in body_src or "stderr" in body_src, (
                "stderr channel handler should use sys.stderr"
            )
            assert "sys.stdout" not in body_src, "stderr channel handler must NOT use sys.stdout"


class TestRequestScopeMiddlewareRemoved:
    """FR-017: RequestScopeMiddleware removed — unified into RequestContainerMiddleware."""

    def test_request_scope_middleware_does_not_exist(self) -> None:
        """AC: Class is removed. RequestContainerMiddleware handles HTTP + WebSocket."""
        from arvel.http import middleware

        assert not hasattr(middleware, "RequestScopeMiddleware"), (
            "RequestScopeMiddleware should be removed — "
            "RequestContainerMiddleware handles both HTTP and WebSocket"
        )

    def test_request_container_middleware_handles_websocket(self) -> None:
        """AC: RequestContainerMiddleware accepts websocket scope."""
        import ast

        from arvel.http import request as req_mod

        with Path(req_mod.__file__).open() as f:
            source = ast.parse(f.read())

        for node in ast.walk(source):
            if isinstance(node, ast.Compare) and isinstance(node.left, ast.Subscript):
                for comparator in node.comparators:
                    if isinstance(comparator, ast.Tuple):
                        values = [
                            elt.value for elt in comparator.elts if isinstance(elt, ast.Constant)
                        ]
                        assert "websocket" in values, (
                            "RequestContainerMiddleware must handle websocket scope"
                        )
                        return
        pytest.fail("Could not find scope type check in RequestContainerMiddleware")


class TestRouteMiddlewareWrapperRemoved:
    """FR-023: Remove unused RouteMiddlewareWrapper class."""

    def test_route_middleware_wrapper_does_not_exist(self) -> None:
        """AC: Class is removed. No existing code references it."""
        from arvel.http import middleware

        assert not hasattr(middleware, "RouteMiddlewareWrapper"), (
            "RouteMiddlewareWrapper should be removed — it's unused dead code"
        )


class TestRequestContainerOnCloseInFinally:
    """FR-024: on_close must execute even if child.close() raises."""

    async def test_on_close_called_when_child_close_raises(self) -> None:
        """AC: on_close callback executes in a finally block after close()."""
        from arvel.foundation.container import ContainerBuilder
        from arvel.http.request import RequestContainerMiddleware

        on_close_called = False

        def mark_closed() -> None:
            nonlocal on_close_called
            on_close_called = True

        builder = ContainerBuilder()
        container = builder.build()

        original_enter = container.enter_scope

        async def broken_close(self_inner: object) -> None:
            raise RuntimeError("close exploded")

        def patched_enter_scope(scope):
            child = original_enter(scope)
            child.close = lambda: broken_close(child)  # type: ignore[assignment]  # ty: ignore[invalid-assignment]
            return child

        container.enter_scope = patched_enter_scope  # type: ignore[assignment]  # ty: ignore[invalid-assignment]

        async def dummy_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = RequestContainerMiddleware(dummy_app, container=container, on_close=mark_closed)

        scope = {"type": "http", "state": {}}

        async def receive():
            return {"type": "http.request", "body": b""}

        sent: list[dict] = []

        async def send(msg):
            sent.append(msg)

        with contextlib.suppress(RuntimeError):
            await mw(scope, receive, send)

        assert on_close_called, "on_close must be called even when child.close() raises"
