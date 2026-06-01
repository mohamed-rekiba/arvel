"""Auto-wiring from constructor type hints, including chains and cycles."""

from __future__ import annotations

import pytest


class A:
    def __init__(self) -> None: ...


class B:
    def __init__(self, a: A) -> None:
        self.a = a


class C:
    def __init__(self, b: B) -> None:
        self.b = b


def test_autowire_simple_chain() -> None:
    from arvel.container import Container

    c = Container()
    obj = c.make(C)
    assert isinstance(obj, C)
    assert isinstance(obj.b, B)
    assert isinstance(obj.b.a, A)


def test_autowire_singleton_propagates_through_chain() -> None:
    from arvel.container import Container

    c = Container()
    c.singleton(A)
    first = c.make(C)
    second = c.make(C)
    assert first is not second
    assert first.b.a is second.b.a


def test_circular_dependency_raises() -> None:
    from arvel.container import CircularDependencyError, Container

    class X:
        def __init__(self, y: Y) -> None:
            self.y = y

    class Y:
        def __init__(self, x: X) -> None:
            self.x = x

    c = Container()
    with pytest.raises(CircularDependencyError) as excinfo:
        c.make(X)
    assert "X" in str(excinfo.value)
    assert "Y" in str(excinfo.value)


def test_unresolvable_dependency_message_includes_path() -> None:
    from arvel.container import BindingResolutionError, Container

    class IDep:
        pass

    class NeedsDep:
        def __init__(self, dep: IDep) -> None:
            self.dep = dep

    c = Container()
    with pytest.raises(BindingResolutionError) as excinfo:
        c.make(NeedsDep)
    msg = str(excinfo.value)
    assert "NeedsDep" in msg
    assert "IDep" in msg


def test_make_with_overrides_uses_supplied_kwarg() -> None:
    from arvel.container import Container

    explicit_a = A()
    c = Container()
    obj = c.make(B, a=explicit_a)
    assert obj.a is explicit_a
