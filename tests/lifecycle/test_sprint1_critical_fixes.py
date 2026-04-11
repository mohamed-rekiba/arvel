"""Sprint 1: Critical Path Fixes — QA-Pre failing tests.

FR-001: DatabaseHealthCheck engine reuse
FR-002: install_exception_handlers wires domain exceptions
FR-003: Application._build_fastapi_app installs exception handlers by default
FR-004: TestBootstrapOrdering actually verifies register-before-boot
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from pathlib import Path

from arvel.data.exceptions import NotFoundError
from arvel.http.exception_handler import install_exception_handlers
from arvel.security.exceptions import AuthenticationError, AuthorizationError


class _FakeConn:
    """Fake async connection that accepts execute() calls."""

    async def execute(self, stmt: object) -> None:
        pass


class _FakeConnCM:
    """Async context manager yielding a _FakeConn."""

    async def __aenter__(self) -> _FakeConn:
        return _FakeConn()

    async def __aexit__(self, *exc: object) -> None:
        pass


class TestDatabaseHealthCheckEngineReuse:
    """FR-001: DatabaseHealthCheck reuses shared engine when provided."""

    async def test_health_check_with_shared_engine_does_not_create_new_engine(self) -> None:
        """AC: Health check with shared engine executes SELECT 1 without creating/disposing."""
        from arvel.observability.integration_health import DatabaseHealthCheck

        dispose_called = False

        class FakeEngine:
            def connect(self):
                return _FakeConnCM()

            async def dispose(self) -> None:
                nonlocal dispose_called
                dispose_called = True

        check = DatabaseHealthCheck(engine=FakeEngine())  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
        result = await check.check()

        assert result.status.value == "healthy"
        assert not dispose_called, "Shared engine should not be disposed"

    async def test_health_check_without_engine_falls_back_to_create_dispose(self) -> None:
        """AC: Health check without shared engine falls back to create + dispose."""
        from arvel.observability.integration_health import DatabaseHealthCheck

        dispose_called = False
        create_called = False

        class FakeEngine:
            def connect(self):
                return _FakeConnCM()

            async def dispose(self) -> None:
                nonlocal dispose_called
                dispose_called = True

        def fake_create_engine(*args: object, **kwargs: object) -> FakeEngine:
            nonlocal create_called
            create_called = True
            return FakeEngine()

        check = DatabaseHealthCheck()

        with patch(
            "sqlalchemy.ext.asyncio.create_async_engine",
            side_effect=fake_create_engine,
        ):
            await check.check()

        assert create_called, "Should create a new engine when none is shared"
        assert dispose_called, "Should dispose the created engine"


class TestExceptionHandlerAutoWiring:
    """FR-002: install_exception_handlers wires domain exceptions automatically."""

    @pytest.fixture
    def app_with_domain_exceptions(self) -> FastAPI:
        app = FastAPI()
        install_exception_handlers(app, debug=False)

        @app.get("/not-found")
        async def not_found() -> None:
            raise NotFoundError("User not found", model_name="User", record_id=42)

        @app.get("/unauthorized")
        async def unauthorized() -> None:
            raise AuthenticationError("Invalid token")

        @app.get("/forbidden")
        async def forbidden() -> None:
            raise AuthorizationError("Insufficient permissions")

        return app

    async def test_not_found_error_returns_404_not_500(
        self, app_with_domain_exceptions: FastAPI
    ) -> None:
        """AC: NotFoundError -> 404, not 500."""
        transport = ASGITransport(app=app_with_domain_exceptions)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/not-found")
            assert resp.status_code == 404, (
                f"Expected 404 but got {resp.status_code}. "
                "install_exception_handlers should wire domain exceptions."
            )
            assert resp.headers["content-type"] == "application/problem+json"

    async def test_authentication_error_returns_401(
        self, app_with_domain_exceptions: FastAPI
    ) -> None:
        """AC: AuthenticationError -> 401."""
        transport = ASGITransport(app=app_with_domain_exceptions)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/unauthorized")
            assert resp.status_code == 401

    async def test_authorization_error_returns_403(
        self, app_with_domain_exceptions: FastAPI
    ) -> None:
        """AC: AuthorizationError -> 403."""
        transport = ASGITransport(app=app_with_domain_exceptions)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/forbidden")
            assert resp.status_code == 403

    async def test_calling_both_functions_is_idempotent(self) -> None:
        """AC: Calling both install_exception_handlers and register_exception works."""
        from arvel.http.exception_handler import register_exception

        app = FastAPI()
        install_exception_handlers(app, debug=False)
        register_exception(app)

        @app.get("/not-found")
        async def not_found() -> None:
            raise NotFoundError("gone", model_name="Item", record_id=99)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/not-found")
            assert resp.status_code == 404


class TestApplicationDefaultExceptionHandlers:
    """FR-003: Application._build_fastapi_app installs exception handlers by default."""

    async def test_booted_app_returns_problem_json_for_domain_exceptions(
        self, tmp_project: Path
    ) -> None:
        """AC: Freshly booted Application returns problem+json for domain exceptions."""
        from arvel.foundation.application import Application

        (tmp_project / "bootstrap" / "providers.py").write_text(
            "from arvel.foundation.provider import ServiceProvider\n\n"
            "class TestProvider(ServiceProvider):\n"
            "    async def boot(self, app):\n"
            "        from arvel.data.exceptions import NotFoundError\n"
            "        @app.asgi_app().get('/test-not-found')\n"
            "        async def handler():\n"
            "            raise NotFoundError(\n"
            "                'missing', model_name='Widget', record_id=1\n"
            "            )\n\n"
            "providers = [TestProvider]\n"
        )

        app = await Application.create(tmp_project, testing=True)
        transport = ASGITransport(app=app.asgi_app())
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/test-not-found")
            assert resp.status_code == 404, (
                f"Expected 404 but got {resp.status_code}. "
                "Application should install exception handlers by default."
            )
            assert resp.headers["content-type"] == "application/problem+json"


class TestBootstrapOrderingActuallyVerified:
    """FR-004: Bootstrap ordering test must actually verify register-before-boot."""

    async def test_register_before_boot_with_recording_providers(self, tmp_project: Path) -> None:
        """AC: Providers record calls; max(register) < min(boot)."""
        from arvel.foundation.application import Application

        (tmp_project / "bootstrap" / "providers.py").write_text(
            "from arvel.foundation.provider import ServiceProvider\n\n"
            "_call_log: list[str] = []\n\n"
            "class AlphaProvider(ServiceProvider):\n"
            "    async def register(self, container):\n"
            "        _call_log.append('register:Alpha')\n\n"
            "    async def boot(self, app):\n"
            "        _call_log.append('boot:Alpha')\n\n"
            "class BetaProvider(ServiceProvider):\n"
            "    async def register(self, container):\n"
            "        _call_log.append('register:Beta')\n\n"
            "    async def boot(self, app):\n"
            "        _call_log.append('boot:Beta')\n\n"
            "providers = [AlphaProvider, BetaProvider]\n"
        )

        app = await Application.create(tmp_project, testing=True)

        providers_module = None
        for provider in app.providers:
            mod = type(provider).__module__
            if mod in sys.modules:
                providers_module = sys.modules[mod]
                break

        assert providers_module is not None, "Could not find providers module"
        call_log = getattr(providers_module, "_call_log", [])

        register_indices = [i for i, c in enumerate(call_log) if c.startswith("register:")]
        boot_indices = [i for i, c in enumerate(call_log) if c.startswith("boot:")]

        assert len(register_indices) >= 2, f"Expected 2+ register calls, got {register_indices}"
        assert len(boot_indices) >= 2, f"Expected 2+ boot calls, got {boot_indices}"
        assert max(register_indices) < min(boot_indices), (
            f"register() must complete before boot(). Log: {call_log}"
        )

    async def test_boot_not_called_before_register_completes(self, tmp_project: Path) -> None:
        """AC: Verify exact ordering: register-register-boot-boot."""
        from arvel.foundation.application import Application

        (tmp_project / "bootstrap" / "providers.py").write_text(
            "from arvel.foundation.provider import ServiceProvider\n\n"
            "_order_log: list[str] = []\n\n"
            "class FirstProvider(ServiceProvider):\n"
            "    priority = 10\n"
            "    async def register(self, container):\n"
            "        _order_log.append('register:First')\n\n"
            "    async def boot(self, app):\n"
            "        _order_log.append('boot:First')\n\n"
            "class SecondProvider(ServiceProvider):\n"
            "    priority = 20\n"
            "    async def register(self, container):\n"
            "        _order_log.append('register:Second')\n\n"
            "    async def boot(self, app):\n"
            "        _order_log.append('boot:Second')\n\n"
            "providers = [FirstProvider, SecondProvider]\n"
        )

        app = await Application.create(tmp_project, testing=True)

        providers_module = None
        for provider in app.providers:
            mod = type(provider).__module__
            if mod in sys.modules:
                providers_module = sys.modules[mod]
                break

        assert providers_module is not None
        order_log = getattr(providers_module, "_order_log", [])

        assert order_log == [
            "register:First",
            "register:Second",
            "boot:First",
            "boot:Second",
        ], f"Expected register-register-boot-boot ordering, got: {order_log}"
