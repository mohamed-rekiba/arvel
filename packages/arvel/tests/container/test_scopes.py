"""FR-001-014: Scopes (singleton, scoped, transient) + scope() / ascope() context managers."""

from __future__ import annotations


class Service:
    def __init__(self) -> None: ...


def test_scoped_caches_within_scope_and_evicts_on_exit() -> None:
    from arvel.container import Container

    c = Container()
    c.scoped(Service)

    with c.scope() as scoped:
        a = scoped.make(Service)
        b = scoped.make(Service)
        assert a is b

    # Outside the scope, a fresh scope produces a new instance
    with c.scope() as scoped2:
        d = scoped2.make(Service)
        assert d is not a


def test_singleton_persists_across_scopes() -> None:
    from arvel.container import Container

    c = Container()
    c.singleton(Service)

    with c.scope() as s1:
        a = s1.make(Service)
    with c.scope() as s2:
        b = s2.make(Service)
    assert a is b


def test_transient_never_cached() -> None:
    from arvel.container import Container

    c = Container()
    c.bind(Service)

    with c.scope() as scoped:
        assert scoped.make(Service) is not scoped.make(Service)


async def test_ascope_works_as_async_context_manager() -> None:
    from arvel.container import Container

    c = Container()
    c.scoped(Service)

    async with c.ascope() as scoped:
        a = scoped.make(Service)
        b = scoped.make(Service)
        assert a is b
