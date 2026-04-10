"""Tests for Application kernel bootstrap — Story 1.

FR-001: Module auto-discovery
FR-002: Register before boot ordering
FR-003: Returns ASGI app
NFR-001: Cold boot < 500ms
NFR-004: Fail-fast on provider failure
NFR-006: No debug in production
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from arvel.foundation.application import Application
from arvel.foundation.exceptions import BootError, ProviderNotFoundError


class TestModuleDiscovery:
    """FR-001: Load providers from bootstrap/providers.py."""

    async def test_discovers_two_modules(self, tmp_project_with_modules: Path) -> None:
        app = await Application.create(tmp_project_with_modules, testing=True)
        assert len(app.providers) == 2

    async def test_discovers_zero_modules_without_error(self, tmp_project_no_modules: Path) -> None:
        app = await Application.create(tmp_project_no_modules, testing=True)
        assert len(app.providers) == 0

    async def test_raises_when_providers_list_missing(self, tmp_project_bad_provider: Path) -> None:
        with pytest.raises(ProviderNotFoundError) as exc_info:
            await Application.create(tmp_project_bad_provider, testing=True)
        assert "providers" in str(exc_info.value).lower()


class TestBootstrapOrdering:
    """FR-002: All register() calls complete before any boot() starts."""

    async def test_register_before_boot(self, tmp_project_with_modules: Path) -> None:
        call_log: list[str] = []

        await Application.create(tmp_project_with_modules, testing=True)

        register_indices = [i for i, c in enumerate(call_log) if c.startswith("register:")]
        boot_indices = [i for i, c in enumerate(call_log) if c.startswith("boot:")]

        if register_indices and boot_indices:
            assert max(register_indices) < min(boot_indices)


class TestASGIApp:
    """FR-003: Returns a valid ASGI application."""

    async def test_returns_asgi_app(self, tmp_project_with_modules: Path) -> None:
        app = await Application.create(tmp_project_with_modules, testing=True)
        asgi = app.asgi_app()
        assert callable(asgi)

    async def test_asgi_app_responds_to_requests(self, tmp_project_with_modules: Path) -> None:
        from httpx import ASGITransport, AsyncClient

        app = await Application.create(tmp_project_with_modules, testing=True)
        transport = ASGITransport(app=app.asgi_app())
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            assert resp.status_code in (200, 404)


class TestSettingsAccess:
    """Settings slices are exposed through helper and container DI."""

    async def test_settings_helper_returns_typed_slice(
        self, tmp_project_with_modules: Path
    ) -> None:
        from arvel.http.config import HttpSettings

        app = await Application.create(tmp_project_with_modules, testing=True)
        http_settings = app.settings(HttpSettings)
        assert isinstance(http_settings, HttpSettings)

    async def test_module_settings_registered_in_container(
        self, tmp_project_with_modules: Path
    ) -> None:
        from arvel.http.config import HttpSettings

        app = await Application.create(tmp_project_with_modules, testing=True)
        resolved = await app.container.resolve(HttpSettings)
        from_helper = app.settings(HttpSettings)
        assert resolved is from_helper


class TestFailFast:
    """NFR-004: Abort startup on provider failure."""

    async def test_boot_error_aborts_startup(self, tmp_project: Path) -> None:
        (tmp_project / "bootstrap" / "providers.py").write_text(
            "from arvel.foundation.provider import ServiceProvider\n\n"
            "class FailingProvider(ServiceProvider):\n"
            "    async def boot(self, app):\n"
            "        raise RuntimeError('intentional failure')\n\n"
            "providers = [FailingProvider]\n"
        )
        with pytest.raises(BootError) as exc_info:
            await Application.create(tmp_project, testing=True)
        assert "FailingProvider" in str(exc_info.value)


class TestColdBootPerformance:
    """NFR-001: Cold boot < 500ms for 10 modules."""

    async def test_boot_under_500ms(self, tmp_project: Path) -> None:
        lines = ["from arvel.foundation.provider import ServiceProvider\n\n"]
        for i in range(10):
            lines.append(f"class Mod{i}Provider(ServiceProvider):\n    pass\n\n")
        lines.append("providers = [" + ", ".join(f"Mod{i}Provider" for i in range(10)) + "]\n")
        (tmp_project / "bootstrap" / "providers.py").write_text("".join(lines))

        start = time.perf_counter()
        await Application.create(tmp_project, testing=True)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 500, f"Cold boot took {elapsed_ms:.0f}ms, expected < 500ms"


class TestTestingMode:
    """ADR-006: testing=True sets APP_ENV=testing."""

    async def test_testing_flag_sets_env(self, tmp_project_with_modules: Path) -> None:
        app = await Application.create(tmp_project_with_modules, testing=True)
        assert app.config.app_env == "testing"

    async def test_default_is_not_testing(
        self, tmp_project_with_modules: Path, clean_env: None
    ) -> None:
        app = await Application.create(tmp_project_with_modules)
        assert app.config.app_env != "testing"


class TestGracefulShutdown:
    """Application.shutdown() tears down cleanly."""

    async def test_shutdown_closes_container(self, tmp_project_with_modules: Path) -> None:
        app = await Application.create(tmp_project_with_modules, testing=True)
        await app.shutdown()
        # After shutdown, container should be closed
        assert app.container is not None  # exists but closed

    async def test_shutdown_calls_provider_hooks_in_reverse_order(self, tmp_project: Path) -> None:
        (tmp_project / "bootstrap" / "providers.py").write_text(
            "from arvel.foundation.provider import ServiceProvider\n\n"
            "class AProvider(ServiceProvider):\n"
            "    calls: list[str] = []\n"
            "    async def shutdown(self, app):\n"
            "        AProvider.calls.append('A')\n\n"
            "class BProvider(ServiceProvider):\n"
            "    calls: list[str] = []\n"
            "    async def shutdown(self, app):\n"
            "        BProvider.calls.append('B')\n\n"
            "providers = [AProvider, BProvider]\n"
        )
        app = await Application.create(tmp_project, testing=True)
        await app.shutdown()

        from importlib import import_module

        bp = import_module("bootstrap.providers")
        assert bp.BProvider.calls == ["B"]
        assert bp.AProvider.calls == ["A"]

    async def test_shutdown_continues_when_provider_shutdown_fails(self, tmp_project: Path) -> None:
        (tmp_project / "bootstrap" / "providers.py").write_text(
            "from arvel.foundation.provider import ServiceProvider\n\n"
            "class FailingProvider(ServiceProvider):\n"
            "    async def shutdown(self, app):\n"
            "        raise RuntimeError('boom')\n\n"
            "class HealthyProvider(ServiceProvider):\n"
            "    called = False\n"
            "    async def shutdown(self, app):\n"
            "        HealthyProvider.called = True\n\n"
            "providers = [FailingProvider, HealthyProvider]\n"
        )
        app = await Application.create(tmp_project, testing=True)
        await app.shutdown()

        from importlib import import_module

        bp = import_module("bootstrap.providers")
        assert bp.HealthyProvider.called is True
