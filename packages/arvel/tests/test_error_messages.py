"""NFR-001-005: Error messages include offending symbol + dependency path + caller name."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_binding_resolution_error_names_offender() -> None:
    from arvel.container import BindingResolutionError, Container

    class IUnbound:
        pass

    class Needs:
        def __init__(self, dep: IUnbound) -> None: ...

    c = Container()
    with pytest.raises(BindingResolutionError) as excinfo:
        c.make(Needs)
    msg = str(excinfo.value)
    assert "IUnbound" in msg
    assert "Needs" in msg


def test_circular_dependency_error_carries_cycle_tuple() -> None:
    from arvel.container import CircularDependencyError, Container

    class A:
        def __init__(self, b: B) -> None: ...

    class B:
        def __init__(self, a: A) -> None: ...

    c = Container()
    with pytest.raises(CircularDependencyError) as excinfo:
        c.make(A)
    assert hasattr(excinfo.value, "cycle")
    cycle_names = [t.__name__ for t in excinfo.value.cycle]
    assert "A" in cycle_names and "B" in cycle_names


def test_boot_error_carries_provider_attribute(tmp_path: Path) -> None:
    from arvel import Application, BootError, ServiceProvider

    class Bad(ServiceProvider):
        async def boot(self) -> None:
            raise RuntimeError("kaboom")

    app = Application.configure(tmp_path).with_environment("testing").with_providers([Bad]).create()
    import asyncio

    with pytest.raises(BootError) as excinfo:
        asyncio.run(app.boot())
    assert excinfo.value.provider is Bad
