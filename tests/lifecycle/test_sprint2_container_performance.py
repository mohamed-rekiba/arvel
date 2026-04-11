"""Sprint 2: Container Performance — QA-Pre tests.

FR-005: ChainMap pattern for enter_scope (O(1) instead of dict copy)
FR-006: Concurrent resolve() returns same instance
FR-007: enter_scope() is synchronous
FR-008: Container.close() disposes instances with close()/aclose()
"""

from __future__ import annotations

import asyncio

import anyio
import pytest

from arvel.foundation.container import Container, ContainerBuilder, Scope


class TestChainMapEnterScope:
    """FR-005: enter_scope() must not copy the full _bindings dict."""

    async def test_enter_scope_is_o1_no_dict_copy(self) -> None:
        """AC: enter_scope() does not copy _bindings — child delegates reads to parent."""
        from collections import ChainMap

        builder = ContainerBuilder()
        for i in range(100):
            t = type(f"Svc{i}", (), {})
            builder.provide(t, t, scope=Scope.REQUEST)
        parent = builder.build()

        child = parent.enter_scope(Scope.REQUEST)

        assert isinstance(child._bindings, ChainMap), "Child should use a ChainMap, not a dict copy"

    async def test_child_resolves_parent_bindings(self) -> None:
        """AC: Child container resolves bindings from parent correctly."""

        class ParentService:
            pass

        builder = ContainerBuilder()
        builder.provide(ParentService, ParentService, scope=Scope.REQUEST)
        parent = builder.build()

        child = parent.enter_scope(Scope.REQUEST)

        instance = await child.resolve(ParentService)
        assert isinstance(instance, ParentService)

    async def test_child_override_does_not_affect_parent(self) -> None:
        """AC: Child can override parent bindings without affecting parent."""

        class SharedService:
            pass

        class ChildOverride(SharedService):
            pass

        builder = ContainerBuilder()
        builder.provide(SharedService, SharedService, scope=Scope.REQUEST)
        parent = builder.build()

        child = parent.enter_scope(Scope.REQUEST)

        child.instance(SharedService, ChildOverride())

        child_instance = await child.resolve(SharedService)
        parent_instance = await parent.resolve(SharedService)

        assert isinstance(child_instance, ChildOverride)
        assert isinstance(parent_instance, SharedService)
        assert type(child_instance) is not type(parent_instance)


class TestConcurrentResolve:
    """FR-006: resolve() must not allow duplicate construction under concurrency."""

    async def test_concurrent_resolve_returns_same_instance(self) -> None:
        """AC: Two concurrent resolve() calls return the same instance."""
        construction_count = 0

        class SlowService:
            pass

        async def slow_factory() -> SlowService:
            nonlocal construction_count
            construction_count += 1
            await anyio.sleep(0.05)
            return SlowService()

        builder = ContainerBuilder()
        builder.provide_factory(SlowService, slow_factory, scope=Scope.REQUEST)
        parent = builder.build()

        child = parent.enter_scope(Scope.REQUEST)

        results: list[SlowService] = []

        async def _resolve() -> None:
            inst = await child.resolve(SlowService)
            results.append(inst)

        async with anyio.create_task_group() as tg:
            tg.start_soon(_resolve)
            tg.start_soon(_resolve)

        assert len(results) == 2
        assert results[0] is results[1], "Concurrent resolve() must return the same instance"
        assert construction_count == 1, (
            f"Expected 1 construction, got {construction_count} — race condition"
        )


class TestSyncEnterScope:
    """FR-007: enter_scope() must be synchronous (not async def)."""

    async def test_enter_scope_callable_without_await(self) -> None:
        """AC: enter_scope() is callable without await."""
        builder = ContainerBuilder()
        parent = builder.build()

        result = parent.enter_scope(Scope.REQUEST)

        is_coroutine = asyncio.iscoroutine(result)
        if is_coroutine:
            await result  # clean up the coroutine  # ty: ignore[invalid-await]
            pytest.fail("enter_scope() should be synchronous (return Container, not coroutine)")

        assert isinstance(result, Container)


class TestContainerCloseDisposesInstances:
    """FR-008: Container.close() must call close()/aclose() on instances."""

    async def test_close_calls_close_on_instances(self) -> None:
        """AC: APP-scoped instance with close() has it called during container.close()."""
        closed = False

        class DisposableService:
            async def close(self) -> None:
                nonlocal closed
                closed = True

        builder = ContainerBuilder()
        builder.provide(DisposableService, DisposableService, scope=Scope.APP)
        container = builder.build()

        await container.resolve(DisposableService)
        await container.close()

        assert closed, "Container.close() should call close() on disposable instances"

    async def test_one_close_failure_does_not_prevent_others(self) -> None:
        """AC: One instance's close() failure doesn't prevent others from closing."""
        second_closed = False

        class FailingService:
            async def close(self) -> None:
                raise RuntimeError("close failed")

        class HealthyService:
            async def close(self) -> None:
                nonlocal second_closed
                second_closed = True

        builder = ContainerBuilder()
        builder.provide(FailingService, FailingService, scope=Scope.APP)
        builder.provide(HealthyService, HealthyService, scope=Scope.APP)
        container = builder.build()

        await container.resolve(FailingService)
        await container.resolve(HealthyService)
        await container.close()

        assert second_closed, (
            "HealthyService.close() should still be called even if FailingService.close() raises"
        )
