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
