"""Extending bindings."""

from __future__ import annotations


class Greeter:
    def greet(self) -> str:
        return "hi"


def test_extend_wraps_resolution() -> None:
    from arvel.container import Container

    c = Container()
    c.bind(Greeter)

    def loud(g: Greeter, _c: Container) -> Greeter:
        g.greet = lambda: "HI!"  # type: ignore[method-assign]
        return g

    c.extend(Greeter, loud)
    assert c.make(Greeter).greet() == "HI!"


def test_extensions_compose_in_registration_order() -> None:
    from arvel.container import Container

    c = Container()
    c.bind(Greeter)

    def exclaim(g: Greeter, _c: Container) -> Greeter:
        original = g.greet
        g.greet = lambda: original() + "!"  # type: ignore[method-assign]
        return g

    def shout(g: Greeter, _c: Container) -> Greeter:
        original = g.greet
        g.greet = lambda: original().upper()  # type: ignore[method-assign]
        return g

    c.extend(Greeter, exclaim)
    c.extend(Greeter, shout)
    assert c.make(Greeter).greet() == "HI!"


class AutoGreeter:
    # Explicit __init__ so the container will auto-wire it without a binding.
    def __init__(self) -> None:
        self.word = "hi"

    def greet(self) -> str:
        return self.word


def test_extend_applies_to_autowired_class() -> None:
    # Unbound concrete classes resolve via auto-wire; extend() must still run.
    from arvel.container import Container

    c = Container()

    def loud(g: AutoGreeter, _c: Container) -> AutoGreeter:
        g.word = "HI!"
        return g

    c.extend(AutoGreeter, loud)
    assert c.make(AutoGreeter).greet() == "HI!"


async def test_extend_applies_to_autowired_class_async() -> None:
    from arvel.container import Container

    c = Container()

    def loud(g: AutoGreeter, _c: Container) -> AutoGreeter:
        g.word = "HI!"
        return g

    c.extend(AutoGreeter, loud)
    resolved = await c.amake(AutoGreeter)
    assert resolved.greet() == "HI!"


def test_extend_applies_to_contextual_resolution() -> None:
    # A dependency injected via a contextual rule must still pass through extend().
    from arvel.container import Container

    class Dep:
        tag = "raw"

    class Consumer:
        def __init__(self, dep: Dep) -> None:
            self.dep = dep

    c = Container()
    c.when(Consumer).needs(Dep).give(Dep)

    def tagged(d: Dep, _c: Container) -> Dep:
        d.tag = "extended"
        return d

    c.extend(Dep, tagged)
    assert c.make(Consumer).dep.tag == "extended"


def test_extend_invalidates_cached_scoped_instance() -> None:
    from arvel.container import Container, Scope

    c = Container()
    c.bind(Greeter, scope=Scope.SCOPED)
    # Prime the scoped cache, then extend — the decorator must run on next make().
    assert c.make(Greeter).greet() == "hi"

    def loud(g: Greeter, _c: Container) -> Greeter:
        g.greet = lambda: "HI!"  # type: ignore[method-assign]
        return g

    c.extend(Greeter, loud)
    assert c.make(Greeter).greet() == "HI!"


def test_extend_applies_to_prebuilt_instance_immediately() -> None:
    # extend() on an instance() registration applies the decorator in place —
    # there's no binding to rebuild from, so it must mutate the stored object.
    from arvel.container import Container

    c = Container()
    base = Greeter()
    c.instance(Greeter, base)

    def loud(g: Greeter, _c: Container) -> Greeter:
        g.greet = lambda: "HI!"  # type: ignore[method-assign]
        return g

    c.extend(Greeter, loud)
    assert c.make(Greeter).greet() == "HI!"


def test_rebind_drops_stale_instance() -> None:
    # Laravel dropStaleInstances: a later bind() must not keep serving the object
    # registered via instance().
    from arvel.container import Container

    class Loud(Greeter):
        def greet(self) -> str:
            return "HI!"

    c = Container()
    c.instance(Greeter, Greeter())
    assert c.make(Greeter).greet() == "hi"

    c.bind(Greeter, Loud)
    assert c.make(Greeter).greet() == "HI!"
