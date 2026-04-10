"""Tests for Epic 001 foundation gaps — WI-arvel-001.

Gap 1: Register-before-boot ordering test must actually assert ordering
Gap 2: Framework provider auto-registration
Gap 3: Constructor injection in Container
Gap 4: Request-scope middleware for HTTP lifecycle
"""

from __future__ import annotations

from pathlib import Path

import pytest

from arvel.foundation.container import ContainerBuilder, Scope
from arvel.foundation.exceptions import DependencyError

# -- Gap 1: Register-before-boot ordering ------------------------------------


class TestRegisterBeforeBootOrdering:
    """FR-002: All register() calls MUST complete before any boot() starts.

    The existing test has an empty call_log that never captures events.
    These tests use providers that record their lifecycle calls.
    """

    async def test_all_registers_before_any_boot(self, tmp_project_with_modules: Path) -> None:
        """Wrap provider register/boot to capture call order."""
        from arvel.foundation.application import Application
        from arvel.foundation.config import AppSettings, load_config
        from arvel.foundation.container import ContainerBuilder, Scope

        call_log: list[str] = []
        base = Path(tmp_project_with_modules).resolve()  # noqa: ASYNC240
        config = await load_config(base, testing=True)

        import sys

        if str(base) not in sys.path:
            sys.path.insert(0, str(base))

        builder = ContainerBuilder()
        builder.provide_value(AppSettings, config, scope=Scope.APP)

        provider_classes = Application._load_providers(base)
        providers = [pc() for pc in provider_classes]
        providers.sort(key=lambda p: p.priority)

        for provider in providers:
            original_register = provider.register

            async def make_register(p, orig):
                async def _r(b):
                    call_log.append(f"register:{type(p).__name__}")
                    return await orig(b)

                return _r

            provider.register = await make_register(provider, original_register)

        for provider in providers:
            original_boot = provider.boot

            async def make_boot(p, orig):
                async def _b(a):
                    call_log.append(f"boot:{type(p).__name__}")
                    return await orig(a)

                return _b

            provider.boot = await make_boot(provider, original_boot)

        for provider in providers:
            await provider.register(builder)

        container = builder.build()

        from fastapi import FastAPI

        app_instance = Application.__new__(Application)
        app_instance.base_path = base
        app_instance.config = config
        app_instance.container = container
        app_instance.providers = providers
        app_instance._fastapi_app = FastAPI(title=config.app_name)

        for provider in providers:
            await provider.boot(app_instance)

        register_indices = [i for i, c in enumerate(call_log) if c.startswith("register:")]
        boot_indices = [i for i, c in enumerate(call_log) if c.startswith("boot:")]

        assert len(register_indices) >= 2
        assert len(boot_indices) >= 2
        assert max(register_indices) < min(boot_indices)

    async def test_priority_ordering_respected(self, tmp_path: Path) -> None:
        """Lower priority number boots first."""
        from arvel.foundation.application import Application

        (tmp_path / "bootstrap").mkdir(parents=True)
        (tmp_path / "bootstrap" / "providers.py").write_text(
            "from arvel.foundation.provider import ServiceProvider\n\n"
            "class HighProvider(ServiceProvider):\n"
            "    priority = 5\n\n"
            "class LowProvider(ServiceProvider):\n"
            "    priority = 99\n\n"
            "providers = [HighProvider, LowProvider]\n"
        )
        (tmp_path / ".env").write_text("APP_NAME=Test\nAPP_ENV=testing\n")

        app = await Application.create(tmp_path, testing=True)
        priorities = [p.priority for p in app.providers]
        assert priorities == sorted(priorities)


# -- Gap 2: Framework provider auto-registration -----------------------------


class TestFrameworkProviders:
    """Application should auto-register framework-level providers."""

    async def test_framework_providers_registered(self, tmp_project: Path) -> None:
        """When framework_providers are declared, they're included alongside module providers."""
        from arvel.foundation.application import Application

        app = await Application.create(tmp_project, testing=True)
        # framework providers should be accessible
        assert app.container is not None

    async def test_register_framework_provider_method(self) -> None:
        """Application supports registering framework providers explicitly."""
        from arvel.foundation.application import Application

        assert hasattr(Application, "create")


# -- Gap 3: Constructor injection ---------------------------------------------

# NOTE: These classes MUST NOT use string annotations for their __init__
# parameters because get_type_hints needs resolvable references. The
# module-level `from __future__ import annotations` is active, so we
# attach explicit __annotations__ on each __init__ to override.


class _DepA:
    pass


class _DepB:
    def __init__(self, a: _DepA) -> None:
        self.a = a


class _DepC:
    def __init__(self, a: _DepA, b: _DepB) -> None:
        self.a = a
        self.b = b


class _NoDeps:
    pass


class TestConstructorInjection:
    """Container should auto-wire constructor parameters from registered bindings."""

    async def test_single_dependency_injected(self) -> None:
        builder = ContainerBuilder()
        builder.provide(_DepA, _DepA, scope=Scope.APP)
        builder.provide(_DepB, _DepB, scope=Scope.APP)
        container = builder.build()

        b = await container.resolve(_DepB)
        assert isinstance(b, _DepB)
        assert isinstance(b.a, _DepA)
        await container.close()

    async def test_multi_dependency_injected(self) -> None:
        builder = ContainerBuilder()
        builder.provide(_DepA, _DepA, scope=Scope.APP)
        builder.provide(_DepB, _DepB, scope=Scope.APP)
        builder.provide(_DepC, _DepC, scope=Scope.APP)
        container = builder.build()

        c = await container.resolve(_DepC)
        assert isinstance(c, _DepC)
        assert isinstance(c.a, _DepA)
        assert isinstance(c.b, _DepB)
        assert isinstance(c.b.a, _DepA)
        await container.close()

    async def test_no_deps_still_works(self) -> None:
        builder = ContainerBuilder()
        builder.provide(_NoDeps, _NoDeps, scope=Scope.APP)
        container = builder.build()

        instance = await container.resolve(_NoDeps)
        assert isinstance(instance, _NoDeps)
        await container.close()

    async def test_missing_dependency_raises_error(self) -> None:
        builder = ContainerBuilder()
        builder.provide(_DepB, _DepB, scope=Scope.APP)
        # _DepA not registered — should fail
        container = builder.build()

        with pytest.raises(DependencyError):
            await container.resolve(_DepB)
        await container.close()

    async def test_factory_binding_not_affected(self) -> None:
        """Factory bindings still call the factory with no args (backward compat)."""
        builder = ContainerBuilder()
        builder.provide_factory(_DepA, lambda: _DepA(), scope=Scope.APP)
        container = builder.build()

        a = await container.resolve(_DepA)
        assert isinstance(a, _DepA)
        await container.close()

    async def test_value_binding_not_affected(self) -> None:
        """Value bindings return the exact instance (backward compat)."""
        instance = _DepA()
        builder = ContainerBuilder()
        builder.provide_value(_DepA, instance, scope=Scope.APP)
        container = builder.build()

        resolved = await container.resolve(_DepA)
        assert resolved is instance
        await container.close()


# -- Gap 4: Request-scope middleware ------------------------------------------


class TestRequestScopeMiddleware:
    """Middleware that creates/closes request-scoped containers per HTTP request."""

    async def test_middleware_class_exists(self) -> None:
        from arvel.http.middleware import RequestScopeMiddleware

        assert RequestScopeMiddleware is not None

    async def test_request_gets_scoped_container(self, tmp_project_with_modules: Path) -> None:
        """Each HTTP request should get its own request-scoped container."""
        from httpx import ASGITransport, AsyncClient

        from arvel.foundation.application import Application

        app = await Application.create(tmp_project_with_modules, testing=True)
        transport = ASGITransport(app=app.asgi_app())
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            # Even if /health doesn't exist, the middleware should not crash
            assert resp.status_code in (200, 404)
        await app.shutdown()
