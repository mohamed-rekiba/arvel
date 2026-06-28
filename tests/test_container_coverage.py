"""Coverage — container DI edge paths: autowire, circular, contextual, scope, call (doc 02)."""

from __future__ import annotations

import abc

import pytest

from arvel.kernel.container import (
    BindingResolutionError,
    CircularDependencyError,
    Container,
)


class Service:
    pass


class NeedsService:
    def __init__(self, service: Service) -> None:
        self.service = service


class Unbuildable(abc.ABC):
    @abc.abstractmethod
    def run(self) -> None: ...


class CircA:
    def __init__(self, b: CircB) -> None:
        self.b = b


class CircB:
    def __init__(self, a: CircA) -> None:
        self.a = a


def test_getitem_and_contains() -> None:
    c = Container()
    c.instance("x", 5)
    assert c["x"] == 5
    assert "x" in c
    assert "y" not in c


def test_autowire_resolves_dependency() -> None:
    c = Container()
    obj = c.make(NeedsService)
    assert isinstance(obj.service, Service)


def test_circular_dependency_detected() -> None:
    c = Container()
    with pytest.raises(CircularDependencyError):
        c.make(CircA)


def test_abstract_target_is_unbuildable() -> None:
    with pytest.raises(BindingResolutionError):
        Container().make(Unbuildable)


def test_default_and_nullable_dependencies() -> None:
    class WithDefault:
        def __init__(self, n: int = 5) -> None:
            self.n = n

    class WithOptionalUnresolvable:
        def __init__(self, dep: Unbuildable | None = None) -> None:
            self.dep = dep

    class NeedsUnresolvable:
        def __init__(self, dep: Unbuildable) -> None:
            self.dep = dep

    c = Container()
    assert c.make(WithDefault).n == 5  # primitive default
    assert c.make(WithOptionalUnresolvable).dep is None  # nullable + unresolvable → None
    with pytest.raises(BindingResolutionError):
        c.make(NeedsUnresolvable)  # required + unresolvable → raise


def test_contextual_literal_binding() -> None:
    c = Container()
    pinned = Service()
    c.when(NeedsService).needs(Service).give(pinned)  # give a literal instance
    assert c.make(NeedsService).service is pinned


def test_scoped_lifecycle() -> None:
    c = Container()
    c.scoped("svc", Service)
    with c.scope():
        a = c.make("svc")
        b = c.make("svc")
        assert a is b  # one instance per scope
    outside = c.make("svc")
    assert outside is not a  # fresh outside the scope


def test_call_autowires_and_honors_params() -> None:
    c = Container()

    def handler(service: Service, count: int = 3) -> tuple[Service, int]:
        return service, count

    svc, count = c.call(handler)
    assert isinstance(svc, Service)
    assert count == 3
    _, count2 = c.call(handler, count=9)
    assert count2 == 9
