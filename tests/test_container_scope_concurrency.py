"""Container depth (doc 01/06) — scoped bindings isolate per scope AND per concurrent async task
(the per-request ContextVar model), while singletons stay shared."""

from __future__ import annotations

import asyncio

from arvel.kernel import Container


class Service:
    pass


def _container() -> Container:
    c = Container()
    c.scoped(Service, lambda _c: Service())
    return c


def test_scoped_shares_within_a_scope_and_differs_across_scopes() -> None:
    c = _container()
    with c.scope():
        a, b = c.make(Service), c.make(Service)
        assert a is b  # one instance per scope
    with c.scope():
        d = c.make(Service)
    assert d is not a  # a fresh scope → a fresh instance


async def test_concurrent_tasks_get_isolated_scoped_instances() -> None:
    c = _container()

    async def worker() -> tuple[int, bool]:
        with c.scope():
            first = c.make(Service)
            await asyncio.sleep(0)  # yield so tasks interleave across the await
            second = c.make(Service)
            return id(first), first is second

    results = await asyncio.gather(*[worker() for _ in range(20)])
    # within each task: the scoped instance is stable across the await
    assert all(stable for _, stable in results)
    # across tasks: every concurrent scope got its OWN instance (no ContextVar bleed)
    assert len({ident for ident, _ in results}) == 20


async def test_singleton_is_shared_across_concurrent_tasks() -> None:
    c = Container()
    c.singleton(Service, lambda _c: Service())

    async def worker() -> int:
        await asyncio.sleep(0)
        return id(c.make(Service))

    idents = await asyncio.gather(*[worker() for _ in range(10)])
    assert len(set(idents)) == 1  # one shared instance regardless of concurrency


def test_scoped_outside_any_scope_builds_each_time() -> None:
    c = _container()
    assert c.make(Service) is not c.make(Service)  # no active scope → transient


def test_scope_as_sync_decorator() -> None:
    c = _container()
    seen: list[bool] = []

    @c.scope()
    def handler() -> None:
        seen.append(c.make(Service) is c.make(Service))  # one instance within the scoped call

    handler()
    handler()
    assert seen == [True, True]


async def test_scope_as_async_decorator_fresh_per_call() -> None:
    c = _container()
    idents: list[int] = []

    @c.scope()
    async def handler() -> None:
        a = c.make(Service)
        await asyncio.sleep(0)
        assert a is c.make(Service)  # stable across the await
        idents.append(id(a))

    await asyncio.gather(handler(), handler(), handler())
    assert len(set(idents)) == 3  # each decorated call ran in its own fresh scope


async def test_scope_as_async_context_manager() -> None:
    c = _container()
    async with c.scope():
        a = c.make(Service)
        await asyncio.sleep(0)
        assert a is c.make(Service)
