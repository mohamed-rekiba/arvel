"""Tests for Service Provider lifecycle — Story 3.

FR-009: Register bindings available during boot
FR-010: Auto-load from provider.py without import
FR-011: Boot in priority order
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.foundation.application import Application
from arvel.foundation.provider import ServiceProvider

if TYPE_CHECKING:
    from pathlib import Path


class TestProviderBindingsAvailableDuringBoot:
    """FR-009: Bindings from register() are available in other providers' boot()."""

    async def test_cross_provider_resolution_in_boot(self, tmp_project: Path) -> None:
        (tmp_project / "bootstrap" / "providers.py").write_text(
            "from arvel.foundation.provider import ServiceProvider\n"
            "from arvel.foundation.container import Scope\n\n"
            "class FooService:\n"
            "    pass\n\n"
            "class ModAProvider(ServiceProvider):\n"
            "    async def register(self, container):\n"
            "        container.provide(FooService, FooService, scope=Scope.APP)\n\n"
            "class ModBProvider(ServiceProvider):\n"
            "    resolved = None\n\n"
            "    async def boot(self, app):\n"
            "        ModBProvider.resolved = await app.container.resolve(FooService)\n\n"
            "providers = [ModAProvider, ModBProvider]\n"
        )

        await Application.create(tmp_project, testing=True)

        from importlib import import_module

        bp = import_module("bootstrap.providers")
        assert bp.ModBProvider.resolved is not None


class TestAutoDiscovery:
    """FR-010: Providers from bootstrap/providers.py load without manual import."""

    async def test_provider_loaded_automatically(self, tmp_project_with_modules: Path) -> None:
        app = await Application.create(tmp_project_with_modules, testing=True)
        provider_names = [type(p).__name__ for p in app.providers]
        assert "UsersProvider" in provider_names
        assert "BillingProvider" in provider_names


class TestBootPriorityOrdering:
    """FR-011: Providers boot in priority order (lower number first)."""

    async def test_lower_priority_boots_first(self, tmp_project: Path) -> None:
        lines = ["from arvel.foundation.provider import ServiceProvider\n\n"]
        class_names: list[str] = []
        for name, priority in [("early", 10), ("late", 90), ("default", 50)]:
            cls_name = f"{name.title()}Provider"
            class_names.append(cls_name)
            lines.append(
                f"class {cls_name}(ServiceProvider):\n"
                f"    priority = {priority}\n\n"
                f"    async def boot(self, app):\n"
                f"        pass\n\n"
            )
        lines.append("providers = [" + ", ".join(class_names) + "]\n")
        (tmp_project / "bootstrap" / "providers.py").write_text("".join(lines))

        app = await Application.create(tmp_project, testing=True)
        priorities = [p.priority for p in app.providers]
        assert priorities == sorted(priorities)


class TestServiceProviderDefaults:
    """ServiceProvider base class defaults."""

    def test_default_priority_is_50(self) -> None:
        provider = ServiceProvider()
        assert provider.priority == 50

    async def test_register_is_noop_by_default(self) -> None:
        from typing import Any, cast

        provider = ServiceProvider()
        await provider.register(cast("Any", None))

    async def test_boot_is_noop_by_default(self) -> None:
        from typing import Any, cast

        provider = ServiceProvider()
        await provider.boot(cast("Any", None))

    async def test_shutdown_is_noop_by_default(self) -> None:
        from typing import Any, cast

        provider = ServiceProvider()
        await provider.shutdown(cast("Any", None))
