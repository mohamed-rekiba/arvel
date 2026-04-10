"""Tests for Service Container (Dishka integration) — Story 2.

FR-004: APP scope singleton
FR-005: REQUEST scope fresh per request
FR-006: SESSION scope shared within session
FR-007: Interface-to-concrete binding
FR-008: Error on missing binding
NFR-003: DI overhead < 1ms per request
"""

from __future__ import annotations

import time
from typing import Protocol

import pytest

from arvel.foundation.container import ContainerBuilder, Scope
from arvel.foundation.exceptions import DependencyError


class GreeterContract(Protocol):
    def greet(self, name: str) -> str: ...


class EnglishGreeter(GreeterContract):
    def greet(self, name: str) -> str:
        return f"Hello, {name}"


class ServiceA:
    pass


class ServiceB:
    def __init__(self, a: ServiceA) -> None:
        self.a = a


class TestSingletonScope:
    """FR-004: APP-scoped binding returns the same instance every time."""

    async def test_app_scope_returns_same_instance(self) -> None:
        builder = ContainerBuilder()
        builder.provide(ServiceA, ServiceA, scope=Scope.APP)
        container = builder.build()

        first = await container.resolve(ServiceA)
        second = await container.resolve(ServiceA)
        third = await container.resolve(ServiceA)

        assert first is second is third
        await container.close()


class TestRequestScope:
    """FR-005: REQUEST-scoped binding returns fresh instance per request scope."""

    async def test_request_scope_different_per_request(self) -> None:
        builder = ContainerBuilder()
        builder.provide(ServiceA, ServiceA, scope=Scope.REQUEST)
        container = builder.build()

        req1 = await container.enter_scope(Scope.REQUEST)
        instance1 = await req1.resolve(ServiceA)
        await req1.close()

        req2 = await container.enter_scope(Scope.REQUEST)
        instance2 = await req2.resolve(ServiceA)
        await req2.close()

        assert instance1 is not instance2
        await container.close()

    async def test_request_scope_same_within_request(self) -> None:
        builder = ContainerBuilder()
        builder.provide(ServiceA, ServiceA, scope=Scope.REQUEST)
        container = builder.build()

        req = await container.enter_scope(Scope.REQUEST)
        first = await req.resolve(ServiceA)
        second = await req.resolve(ServiceA)
        assert first is second
        await req.close()
        await container.close()


class TestSessionScope:
    """FR-006: SESSION-scoped binding shared within same session."""

    async def test_session_scope_shared_across_requests(self) -> None:
        builder = ContainerBuilder()
        builder.provide(ServiceA, ServiceA, scope=Scope.SESSION)
        container = builder.build()

        session = await container.enter_scope(Scope.SESSION)

        req1 = await session.enter_scope(Scope.REQUEST)
        instance1 = await req1.resolve(ServiceA)
        await req1.close()

        req2 = await session.enter_scope(Scope.REQUEST)
        instance2 = await req2.resolve(ServiceA)
        await req2.close()

        assert instance1 is instance2
        await session.close()
        await container.close()


class TestInterfaceBinding:
    """FR-007: Interface bound to concrete returns concrete on resolution."""

    async def test_protocol_resolves_to_concrete(self) -> None:
        builder = ContainerBuilder()
        builder.provide(GreeterContract, EnglishGreeter, scope=Scope.APP)
        container = builder.build()

        greeter = await container.resolve(GreeterContract)
        assert isinstance(greeter, EnglishGreeter)
        assert greeter.greet("World") == "Hello, World"
        await container.close()


class TestMissingBinding:
    """FR-008: Clear error on unsatisfied dependency."""

    async def test_missing_binding_raises_dependency_error(self) -> None:
        builder = ContainerBuilder()
        container = builder.build()

        with pytest.raises(DependencyError) as exc_info:
            await container.resolve(ServiceA)
        assert "ServiceA" in str(exc_info.value)
        await container.close()


class TestProvideValue:
    """ContainerBuilder.provide_value binds pre-built instances."""

    async def test_provide_value_returns_exact_instance(self) -> None:
        instance = ServiceA()
        builder = ContainerBuilder()
        builder.provide_value(ServiceA, instance, scope=Scope.APP)
        container = builder.build()

        resolved = await container.resolve(ServiceA)
        assert resolved is instance
        await container.close()


class TestDIPerformance:
    """NFR-003: DI resolution overhead < 1ms per request."""

    async def test_resolution_under_1ms(self) -> None:
        builder = ContainerBuilder()
        builder.provide(ServiceA, ServiceA, scope=Scope.REQUEST)
        container = builder.build()

        req = await container.enter_scope(Scope.REQUEST)

        start = time.perf_counter()
        await req.resolve(ServiceA)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 1.0, f"Resolution took {elapsed_ms:.3f}ms, expected < 1ms"
        await req.close()
        await container.close()
