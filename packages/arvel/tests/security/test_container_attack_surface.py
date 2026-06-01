""": container cannot be exploited for arbitrary code execution."""

from __future__ import annotations

import pytest


def test_make_rejects_string_abstract() -> None:
    from arvel.container import Container

    c = Container()
    with pytest.raises((TypeError, ValueError)):
        c.make("os.system")  # type: ignore[arg-type]


def test_make_does_not_autoload_arbitrary_module_attributes() -> None:
    """Auto-wiring must NOT touch sys.modules or perform string import."""
    from arvel.container import BindingResolutionError, Container

    class UnboundProtocol:
        pass

    c = Container()
    with pytest.raises(BindingResolutionError):
        c.make(UnboundProtocol)


def test_init_subclass_does_not_get_silently_instantiated() -> None:
    """Defining a class with __init_subclass__ must not register it with the container."""
    from arvel.container import BindingResolutionError, Container

    calls: list[type] = []

    class TrackedBase:
        def __init_subclass__(cls, **_kw: object) -> None:
            calls.append(cls)

    class Child(TrackedBase):
        pass

    assert calls == [Child]  # subclass got registered, but container didn't touch it
    c = Container()
    with pytest.raises(BindingResolutionError):
        c.make(TrackedBase)
