"""FR-001-015: Async resolution + AsyncBindingError."""

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
