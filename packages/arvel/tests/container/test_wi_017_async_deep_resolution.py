"""WI-arvel-017 — amake must resolve async bindings at any depth, with cycle detection.

The async resolver previously delegated auto-wiring to the sync path, so a
transitive async-bound dependency raised even under amake.
"""

from __future__ import annotations

import pytest
from arvel.container import (
    AsyncBindingError,
    BindingResolutionError,
    CircularDependencyError,
    Container,
)


class Db:
    def __init__(self) -> None:
        self.ready = True


class Repo:
    def __init__(self, db: Db) -> None:
        self.db = db


class Service:
    def __init__(self, repo: Repo) -> None:
        self.repo = repo


async def _db_factory() -> Db:
    return Db()


async def test_amake_resolves_transitive_async_dependency() -> None:
    c = Container()
    c.bind(Db, _db_factory)  # async-bound, two levels below Service
    svc = await c.amake(Service)
    assert isinstance(svc, Service)
    assert svc.repo.db.ready is True


async def test_amake_resolves_async_dep_through_bound_concrete_class() -> None:
    c = Container()
    c.bind(Db, _db_factory)
    c.bind(Repo)  # concrete-class binding whose dep is async
    repo = await c.amake(Repo)
    assert isinstance(repo, Repo)
    assert repo.db.ready is True


def test_sync_make_still_rejects_async_dependency() -> None:
    c = Container()
    c.bind(Db, _db_factory)
    with pytest.raises(BindingResolutionError) as exc_info:
        c.make(Repo)
    assert isinstance(exc_info.value.__cause__, AsyncBindingError)


async def test_amake_detects_circular_dependency() -> None:
    class A:
        def __init__(self, b: B) -> None: ...

    class B:
        def __init__(self, a: A) -> None: ...

    c = Container()
    with pytest.raises(CircularDependencyError):
        await c.amake(A)


async def test_amake_resolves_async_contextual_concrete_class() -> None:
    class Consumer:
        def __init__(self, repo: Repo) -> None:
            self.repo = repo

    c = Container()
    c.bind(Db, _db_factory)
    # Consumer gets a Repo whose own dep (Db) is async-bound.
    c.when(Consumer).needs(Repo).give(Repo)
    consumer = await c.amake(Consumer)
    assert consumer.repo.db.ready is True
