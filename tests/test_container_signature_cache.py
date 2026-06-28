"""Container — autowiring memoizes init signature/type-hints introspection.

``get_type_hints`` is expensive and pure per class; the container caches it so DI
resolution doesn't re-introspect on every ``make``. Correctness must be unchanged.
"""

from __future__ import annotations

from arvel.kernel import Container
from arvel.kernel.container import _init_signature


class Widget:
    pass


class Gadget:
    def __init__(self, widget: Widget) -> None:
        self.widget = widget


class Gizmo:
    def __init__(self, widget: Widget, gadget: Gadget) -> None:
        self.widget = widget
        self.gadget = gadget


class NoIntrospect:
    """A type whose __init__ can't be introspected falls back to no-arg build."""

    __init__ = object.__init__  # signature/get_type_hints may reject this


def test_autowiring_resolves_after_caching() -> None:
    c = Container()
    gizmo = c.make(Gizmo)
    assert isinstance(gizmo.widget, Widget)
    assert isinstance(gizmo.gadget, Gadget)
    assert isinstance(gizmo.gadget.widget, Widget)


def test_distinct_classes_do_not_collide_in_cache() -> None:
    c = Container()
    gadget = c.make(Gadget)
    gizmo = c.make(Gizmo)
    # different signatures resolved correctly — no cross-contamination
    assert isinstance(gadget, Gadget) and not hasattr(gadget, "gadget")
    assert isinstance(gizmo, Gizmo) and isinstance(gizmo.gadget, Gadget)


def test_second_resolution_hits_the_cache() -> None:
    _init_signature.cache_clear()
    c = Container()
    c.make(Gadget)
    misses_after_first = _init_signature.cache_info().misses
    c.make(Gadget)
    info = _init_signature.cache_info()
    assert info.hits >= 1  # the second build reused the cached introspection
    assert info.misses == misses_after_first  # no new miss for the same class


def test_uninspectable_init_still_constructs() -> None:
    c = Container()
    assert isinstance(c.make(NoIntrospect), NoIntrospect)
