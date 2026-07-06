"""Container semantics: rebind drops stale instances (+ rebinding hooks), global
resolving callbacks, positional-only call(), scoped param overrides, and
contextual primitive/name bindings."""

from __future__ import annotations

from arvel.kernel.container import Container


class Box:
    def __init__(self, v: int = 0) -> None:
        self.v = v


class Wants:
    def __init__(self, name: str = "anon", size: int = 1) -> None:
        self.name = name
        self.size = size


# --- rebind drops the stale cached instance ------------------------------
def test_rebind_after_resolve_drops_cached_singleton() -> None:
    c = Container()
    c.singleton("box", lambda app: Box(1))
    assert c.make("box").v == 1
    c.singleton("box", lambda app: Box(2))
    assert c.make("box").v == 2


def test_rebind_over_instance_registration_wins() -> None:
    c = Container()
    c.instance("box", Box(1))
    c.bind("box", lambda app: Box(2))
    assert c.make("box").v == 2


def test_rebind_drops_current_scope_cache() -> None:
    c = Container()
    c.scoped("box", lambda app: Box(1))
    with c.scope():
        assert c.make("box").v == 1
        c.scoped("box", lambda app: Box(2))
        assert c.make("box").v == 2


# --- rebinding callbacks --------------------------------------------------
def test_rebinding_fires_on_rebind_not_first_bind() -> None:
    c = Container()
    fired: list[str] = []
    c.rebinding("box", lambda app: fired.append("rebound"))
    c.bind("box", lambda app: Box(1))
    assert fired == []
    c.bind("box", lambda app: Box(2))
    assert fired == ["rebound"]


def test_rebinding_fires_when_instance_repoints_a_binding() -> None:
    c = Container()
    fired: list[str] = []
    c.bind("box", lambda app: Box(1))
    c.rebinding("box", lambda app: fired.append("rebound"))
    c.instance("box", Box(9))
    assert fired == ["rebound"]
    assert c.make("box").v == 9


# --- global resolving callbacks -------------------------------------------
def test_global_resolving_fires_for_every_resolution_before_keyed() -> None:
    c = Container()
    order: list[str] = []
    c.resolving(lambda obj, app: order.append("global"))
    c.resolving(Box, lambda obj, app: order.append("keyed"))
    c.after_resolving(lambda obj, app: order.append("global-after"))
    c.after_resolving(Box, lambda obj, app: order.append("keyed-after"))
    c.make(Box)
    assert order == ["global", "keyed", "global-after", "keyed-after"]


def test_global_resolving_fires_for_scoped_and_factory_bindings() -> None:
    c = Container()
    seen: list[object] = []
    c.resolving(lambda obj, app: seen.append(obj))
    c.bind("box", lambda app: Box(3))
    c.make("box")
    assert len(seen) == 1 and isinstance(seen[0], Box)


# --- call() with positional-only parameters --------------------------------
def test_call_injects_positional_only_dependency() -> None:
    c = Container()

    def handler(box: Box, /, label: str = "x") -> str:
        return f"{type(box).__name__}:{label}"

    assert c.call(handler) == "Box:x"


def test_call_passes_explicit_params_to_positional_only() -> None:
    c = Container()

    def handler(box: Box, n: int, /) -> int:
        return box.v + n

    assert c.call(handler, box=Box(1), n=2) == 3


# --- scoped bindings + explicit params -------------------------------------
def test_scoped_make_with_params_builds_fresh_and_does_not_cache() -> None:
    c = Container()
    c.scoped(Box)
    with c.scope():
        plain = c.make(Box)
        custom = c.make(Box, v=7)
        assert custom.v == 7
        assert custom is not plain
        assert c.make(Box) is plain  # scope cache still serves the plain one


# --- contextual primitive / name bindings -----------------------------------
def test_contextual_name_binding_injects_primitive() -> None:
    c = Container()
    c.when(Wants).needs("name").give("alice")
    got = c.make(Wants)
    assert got.name == "alice"
    assert got.size == 1  # untouched param keeps its default


def test_contextual_type_binding_injects_primitive_annotation() -> None:
    c = Container()
    c.when(Wants).needs(int).give(5)
    assert c.make(Wants).size == 5


def test_contextual_name_wins_over_type_binding() -> None:
    c = Container()
    c.when(Wants).needs(str).give("by-type")
    c.when(Wants).needs("name").give("by-name")
    assert c.make(Wants).name == "by-name"


def test_contextual_primitive_factory_receives_container() -> None:
    c = Container()
    c.instance("app.name", "arvel")
    c.when(Wants).needs("name").give(lambda app: app.make("app.name"))
    assert c.make(Wants).name == "arvel"


def test_explicit_params_beat_contextual_bindings() -> None:
    c = Container()
    c.when(Wants).needs("name").give("ctx")
    assert c.make(Wants, name="direct").name == "direct"


# --- hardening edges (review findings) --------------------------------------
def test_first_time_instance_does_not_fire_rebinding() -> None:
    c = Container()
    fired: list[str] = []
    c.rebinding("box", lambda app: fired.append("rebound"))
    c.instance("box", Box(1))
    assert fired == []


def test_instance_wins_over_scoped_binding() -> None:
    c = Container()
    c.scoped("box", lambda app: Box(1))
    with c.scope():
        c.instance("box", Box(9))
        assert c.make("box").v == 9


def test_global_after_resolving_alone_fires() -> None:
    c = Container()
    seen: list[object] = []
    c.after_resolving(lambda obj, app: seen.append(obj))
    c.make(Box)
    assert len(seen) == 1


def test_call_unresolvable_positional_only_raises_not_shifts() -> None:
    import pytest

    from arvel.kernel.container import BindingResolutionError

    c = Container()

    def handler(items: list[str], box: Box, /) -> None:  # generics aren't injectable → unresolvable
        raise AssertionError("must not be called")

    with pytest.raises(BindingResolutionError, match="positional-only"):
        c.call(handler)
