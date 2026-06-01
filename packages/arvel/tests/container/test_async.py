"""Async resolution + AsyncBindingError."""

from __future__ import annotations

import pytest


class Service:
    def __init__(self) -> None:
        self.async_built = False


async def test_amake_awaits_async_factory() -> None:
    from arvel.container import Container

    async def factory() -> Service:
        s = Service()
        s.async_built = True
        return s

    c = Container()
    c.bind(Service, factory)
    obj = await c.amake(Service)
    assert isinstance(obj, Service)
    assert obj.async_built is True


def test_make_on_async_binding_raises_async_binding_error() -> None:
    from arvel.container import AsyncBindingError, Container

    async def factory() -> Service:
        return Service()

    c = Container()
    c.bind(Service, factory)
    with pytest.raises(AsyncBindingError):
        c.make(Service)


async def test_amake_falls_back_to_sync_for_sync_bindings() -> None:
    from arvel.container import Container

    c = Container()
    c.bind(Service)
    obj = await c.amake(Service)
    assert isinstance(obj, Service)


class Dep:
    def __init__(self) -> None:
        self.tag = "dep"


class Handler:
    def run(self, dep: Dep, *, label: str) -> str:
        return f"{label}:{dep.tag}"


async def test_acall_injects_bound_dependency_and_honours_overrides() -> None:
    from arvel.container import Container

    c = Container()
    c.bind(Dep)
    # `dep` is type-resolved from the container; `label` comes from overrides.
    result = await c.acall(Handler, "run", overrides={"label": "hi"})
    assert result == "hi:dep"


class UnboundHandler:
    def run(self, missing: Service) -> str:
        # `missing` is unbound, so acall leaves it out and the call would fail
        # unless supplied via overrides. Here we pass it explicitly.
        return f"got:{type(missing).__name__}"


async def test_acall_skips_unbound_param_uses_override() -> None:
    from arvel.container import Container

    c = Container()
    result = await c.acall(UnboundHandler, "run", overrides={"missing": Service()})
    assert result == "got:Service"
