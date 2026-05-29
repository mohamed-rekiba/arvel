"""FR-001-010: Container basic API — bind, singleton, scoped, instance, alias, introspection."""

from __future__ import annotations

import pytest


class Foo:
    def __init__(self) -> None:
        self.created = True


class Bar:
    def __init__(self) -> None: ...


def test_bind_and_make_returns_concrete_instance() -> None:
    from arvel.container import Container

    c = Container()
    c.bind(Foo)
    obj = c.make(Foo)
    assert isinstance(obj, Foo)


def test_bind_with_explicit_concrete() -> None:
    from arvel.container import Container

    class IFoo:
        pass

    class FooImpl(IFoo):
        pass

    c = Container()
    c.bind(IFoo, FooImpl)
    obj = c.make(IFoo)
    assert isinstance(obj, FooImpl)


def test_singleton_caches_instance() -> None:
    from arvel.container import Container

    c = Container()
    c.singleton(Foo)
    a = c.make(Foo)
    b = c.make(Foo)
    assert a is b


def test_transient_creates_new_each_time() -> None:
    from arvel.container import Container

    c = Container()
    c.bind(Foo)
    assert c.make(Foo) is not c.make(Foo)


def test_instance_returns_same_object() -> None:
    from arvel.container import Container

    c = Container()
    pre_built = Foo()
    c.instance(Foo, pre_built)
    assert c.make(Foo) is pre_built


def test_bound_returns_true_after_bind() -> None:
    from arvel.container import Container

    c = Container()
    assert not c.bound(Foo)
    c.bind(Foo)
    assert c.bound(Foo)


def test_resolved_returns_true_after_make_singleton() -> None:
    from arvel.container import Container

    c = Container()
    c.singleton(Foo)
    assert not c.resolved(Foo)
    c.make(Foo)
    assert c.resolved(Foo)


def test_make_unbound_concrete_class_autowires() -> None:
    from arvel.container import Container

    c = Container()
    obj = c.make(Bar)
    assert isinstance(obj, Bar)


def test_make_unbound_abstract_raises_binding_error() -> None:
    from arvel.container import BindingResolutionError, Container

    class IFoo:
        pass

    c = Container()
    with pytest.raises(BindingResolutionError):
        c.make(IFoo)
