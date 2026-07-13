"""Container — autowiring, singletons, scopes, contextual bindings, tags, hooks.

Fixture classes are module-level so ``typing.get_type_hints`` resolves their annotations
under ``from __future__``.
"""

from __future__ import annotations

import inspect

import pytest

from arvel.kernel import BindingResolutionError, CircularDependencyError, Container


class Engine:
    pass


class Car:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine


class Disk:
    pass


class S3Disk(Disk):
    pass


class PhotoController:
    def __init__(self, disk: Disk) -> None:
        self.disk = disk


class NeedsInt:
    def __init__(self, x: int) -> None:
        self.x = x


class MaybeEngine:
    def __init__(self, engine: Engine | None) -> None:
        self.engine = engine


class MaybeInt:
    def __init__(self, x: int | None) -> None:
        self.x = x


class Cyclic1:
    def __init__(self, other: Cyclic2) -> None: ...


class Cyclic2:
    def __init__(self, other: Cyclic1) -> None: ...


def test_bind_and_make() -> None:
    c = Container()
    c.bind("greeting", lambda: "hello")
    assert c.make("greeting") == "hello"


def test_singleton_returns_same_instance() -> None:
    c = Container()
    c.singleton(Engine)
    assert c.make(Engine) is c.make(Engine)


def test_transient_returns_new_each_time() -> None:
    c = Container()
    c.bind(Engine)
    assert c.make(Engine) is not c.make(Engine)


def test_instance_and_alias() -> None:
    c = Container()
    e = Engine()
    c.instance(Engine, e)
    c.alias("engine", Engine)
    assert c.make("engine") is e


def test_autowiring_recurses() -> None:
    c = Container()
    car = c.make(Car)
    assert isinstance(car, Car)
    assert isinstance(car.engine, Engine)


def test_circular_dependency_raises() -> None:
    c = Container()
    with pytest.raises(CircularDependencyError):
        c.make(Cyclic1)


def test_unbound_string_raises() -> None:
    c = Container()
    with pytest.raises(BindingResolutionError):
        c.make("nope")


def test_primitive_without_default_raises() -> None:
    c = Container()
    with pytest.raises(BindingResolutionError):
        c.make(NeedsInt)


def test_optional_resolvable_dependency_is_resolved() -> None:
    # `Engine | None` is resolvable (Engine is buildable) → resolve it, don't null it.
    c = Container()
    obj = c.make(MaybeEngine)
    assert isinstance(obj.engine, Engine)


def test_optional_unresolvable_dependency_falls_back_to_none() -> None:
    # `int | None` is not resolvable (primitive) and has no default → None.
    c = Container()
    obj = c.make(MaybeInt)
    assert obj.x is None


def test_contextual_binding() -> None:
    c = Container()
    c.when(PhotoController).needs(Disk).give(S3Disk)
    pc = c.make(PhotoController)
    assert isinstance(pc.disk, S3Disk)


def test_extend() -> None:
    c = Container()
    c.bind("n", lambda: 1)
    c.extend("n", lambda obj, _c: obj + 10)
    assert c.make("n") == 11


def test_tagging() -> None:
    c = Container()
    c.singleton(Engine)
    c.bind(Car)
    c.tag([Engine, Car], "parts")
    parts = c.tagged("parts")
    assert len(parts) == 2
    assert any(isinstance(p, Engine) for p in parts)


def test_resolving_hook_fires() -> None:
    c = Container()
    seen: list[object] = []
    c.resolving(Engine, lambda obj, _c: seen.append(obj))
    c.make(Engine)
    assert len(seen) == 1


def test_scoped_shares_within_scope_only() -> None:
    c = Container()
    c.scoped(Engine)
    with c.scope():
        a, b = c.make(Engine), c.make(Engine)
        assert a is b
    with c.scope():
        assert c.make(Engine) is not a


def test_make_with_param_override() -> None:
    c = Container()
    car = c.make(Car, engine="OVERRIDE")
    assert car.engine == "OVERRIDE"


async def test_call_is_async_aware() -> None:
    c = Container()

    async def handler(engine: Engine) -> str:
        assert isinstance(engine, Engine)
        return "ok"

    result = c.call(handler)
    assert inspect.iscoroutine(result)
    assert await result == "ok"


def test_call_sync_injects() -> None:
    c = Container()

    def describe(car: Car) -> str:
        return type(car.engine).__name__

    assert c.call(describe) == "Engine"
