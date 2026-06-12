"""Container basic API — bind, singleton, scoped, instance, introspection."""

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


def test_factory_binding_receives_make_overrides() -> None:
    # make(**overrides) must forward to a factory that declares the parameter
    # (Laravel passes explicit params to the binding closure).
    from arvel.container import Container

    class Widget:
        def __init__(self, color: str) -> None:
            self.color = color

    c = Container()
    c.bind(Widget, lambda color="default": Widget(color))
    assert c.make(Widget, color="red").color == "red"
    assert c.make(Widget).color == "default"


def test_zero_arg_factory_ignores_overrides() -> None:
    # A zero-arg factory (the common convention) must keep working even when
    # overrides are passed — they simply don't apply.
    from arvel.container import Container

    c = Container()
    c.bind(Foo, lambda: Foo())
    assert c.make(Foo, unused="x").created is True


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


def test_bind_if_only_binds_when_unbound() -> None:
    from arvel.container import Container

    class FooSub(Foo):
        pass

    c = Container()
    c.bind(Foo, FooSub)
    c.bind_if(Foo, Foo)  # no-op — already bound
    assert isinstance(c.make(Foo), FooSub)

    c2 = Container()
    c2.bind_if(Foo, Foo)  # binds — nothing there yet
    assert isinstance(c2.make(Foo), Foo)


def test_singleton_if_registers_shared_only_when_absent() -> None:
    from arvel.container import Container

    c = Container()
    c.singleton_if(Foo)
    first = c.make(Foo)
    c.singleton_if(Foo)  # no-op
    assert c.make(Foo) is first


def test_scoped_if_registers_scoped_only_when_absent() -> None:
    from arvel.container import Container

    c = Container()
    c.scoped_if(Foo)
    with c.scope() as scoped:
        a = scoped.make(Foo)
        b = scoped.make(Foo)
        assert a is b
