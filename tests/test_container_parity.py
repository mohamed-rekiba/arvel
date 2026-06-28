"""C1-C4 — service-container parity (knowledge/port/02-container.md §16, §131-132):
extend-after-resolve, after_resolving hook, bind_method, resolving-fires-for-scoped."""

from __future__ import annotations

from typing import Any

from arvel.kernel.container import Container


class Box:
    def __init__(self, v: int = 0) -> None:
        self.v = v


# --- C1: extend() after a singleton is resolved -----------------------------
def test_extend_after_resolved_singleton_transforms_cached_instance() -> None:  # C1a
    c = Container()
    c.singleton("box", lambda app: Box(1))
    first = c.make("box")
    c.extend("box", lambda obj, app: (setattr(obj, "v", 99), obj)[1])
    assert c.make("box").v == 99
    assert c.make("box") is first  # same cached instance, transformed in place


def test_extend_before_resolve_applies_at_build() -> None:  # C1b
    c = Container()
    c.singleton("box", lambda app: Box(1))
    c.extend("box", lambda obj, app: (setattr(obj, "v", 7), obj)[1])
    assert c.make("box").v == 7


# --- C2: after_resolving ----------------------------------------------------
def test_after_resolving_fires_after_resolving() -> None:  # C2
    c = Container()
    order: list[str] = []
    c.resolving(Box, lambda obj, app: order.append("resolving"))
    c.after_resolving(Box, lambda obj, app: order.append("after"))
    c.make(Box)
    assert order == ["resolving", "after"]


# --- C3: bind_method --------------------------------------------------------
def test_bind_method_overrides_call() -> None:  # C3
    class Job:
        def handle(self) -> str:
            return "real"

    c = Container()
    c.bind_method([Job, "handle"], lambda job, app: "bound")
    assert c.call((Job(), "handle")) == "bound"


def test_unbound_method_resolves_normally() -> None:  # C3 (negative)
    class Job:
        def handle(self) -> str:
            return "real"

    assert Container().call((Job(), "handle")) == "real"


# --- C4: resolving fires for scoped builds ----------------------------------
def test_resolving_fires_for_scoped_build() -> None:  # C4
    c = Container()
    seen: list[Any] = []
    c.scoped("svc", lambda app: Box(5))
    c.resolving("svc", lambda obj, app: seen.append(obj))
    c.after_resolving("svc", lambda obj, app: seen.append("after"))
    with c.scope():
        c.make("svc")
        c.make("svc")  # cached within scope → fires once
    assert len(seen) == 2  # one resolving + one after, fired on the single build
    assert isinstance(seen[0], Box)
    assert seen[1] == "after"
