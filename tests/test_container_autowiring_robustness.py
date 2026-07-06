"""Container autowiring on non-trivial ctor shapes.

These shapes (``Any``-typed, keyword-only, unresolvable forward-ref params) previously leaked raw
``TypeError``/``NameError`` out of ``make()``; they land on the real default middleware, so each is
verified both synthetically and against ``StartSession``/``ThrottleRequests`` via ``app.make()``.
"""

from __future__ import annotations

from typing import Any

import pytest

from arvel.kernel import BindingResolutionError, Container


class _Dep:
    pass


class _Exploding:
    def __init__(self) -> None:
        raise TypeError("boom in __init__")


class _CycA:
    def __init__(self, b: _CycB | None = None) -> None:
        self.b = b


class _CycB:
    def __init__(self, a: _CycA | None = None) -> None:
        self.a = a


# --- M1: Any-typed params ----------------------------------------------------


def test_any_typed_param_with_default_falls_back() -> None:
    class NeedsAny:
        def __init__(self, cache: Any = None) -> None:
            self.cache = cache

    obj = Container().make(NeedsAny)
    assert obj.cache is None  # Any is non-injectable → default used, no TypeError


def test_any_typed_param_without_default_raises_clear_error() -> None:
    class NeedsAny:
        def __init__(self, x: Any) -> None:
            self.x = x

    with pytest.raises(BindingResolutionError):  # not a raw TypeError
        Container().make(NeedsAny)


# --- M2: keyword-only params -------------------------------------------------


def test_keyword_only_param_is_passed_as_kwarg() -> None:
    class KwOnly:
        def __init__(self, a: int = 1, *, b: str = "z") -> None:
            self.a, self.b = a, b

    obj = Container().make(KwOnly)  # previously: "takes 2 positional args but 3 were given"
    assert (obj.a, obj.b) == (1, "z")


def test_keyword_only_dependency_is_injected_by_type() -> None:
    class KwOnlyDep:
        def __init__(self, *, dep: _Dep) -> None:
            self.dep = dep

    obj = Container().make(KwOnlyDep)
    assert isinstance(obj.dep, _Dep)  # injected via kwargs, not positionally


# --- C3: unresolvable forward-ref hints --------------------------------------
# Built via exec so the deliberately-unresolvable annotation isn't analyzed by the type checkers
# (it must fail at runtime get_type_hints, which is the whole point — no static suppression needed).


def _class_with_bad_forward_ref(*, with_default: bool) -> type[Any]:
    default = " = None" if with_default else ""
    src = f"class BadRef:\n    def __init__(self, dep: 'DoesNotExist'{default}):\n        self.dep = dep\n"
    namespace: dict[str, Any] = {}
    exec(src, namespace)  # noqa: S102 - test fixture: deliberately constructs an unresolvable hint
    return namespace["BadRef"]


def test_forward_ref_with_default_falls_back() -> None:
    obj: Any = Container().make(_class_with_bad_forward_ref(with_default=True))
    assert obj.dep is None  # NameError no longer escapes get_type_hints; default used


def test_forward_ref_without_default_raises_clear_error() -> None:
    with pytest.raises(BindingResolutionError):  # not a raw NameError
        Container().make(_class_with_bad_forward_ref(with_default=False))


# --- the real payoff: default middleware autowire via the container ----------


# --- the fallback must not mask real errors ------------------


def test_real_typeerror_in_dependency_is_not_masked() -> None:
    # a genuine error in a buildable dependency's __init__ must propagate, not be swallowed as
    # "unresolvable → use default"
    class Consumer:
        def __init__(self, dep: _Exploding | None = None) -> None:
            self.dep = dep

    with pytest.raises(TypeError, match="boom"):
        Container().make(Consumer)


def test_cycle_with_defaults_still_raises() -> None:
    from arvel.kernel import CircularDependencyError

    # both cycle params have defaults — the cycle must still be fatal, never silently defaulted.
    with pytest.raises(CircularDependencyError):
        Container().make(_CycA)


def test_default_middleware_autowire_via_container() -> None:
    # both have keyword-only + Any-typed ctor params; the HTTP kernel builds them via app.make(cls)
    from arvel.http.middleware import StartSession, ThrottleRequests
    from arvel.kernel import Application

    app = Application()
    assert isinstance(app.make(StartSession), StartSession)
    assert isinstance(app.make(ThrottleRequests), ThrottleRequests)


def test_unbound_protocol_param_falls_back_to_default() -> None:
    from typing import Protocol

    class Repo(Protocol):
        def all(self) -> list[str]: ...

    class Service:
        def __init__(self, repo: Repo | None = None) -> None:
            self.repo = repo

    c = Container()
    # an unbound Protocol dep is not instantiable; the optional param takes its default
    assert c.make(Service).repo is None


def test_make_unbound_protocol_raises_resolution_error_not_typeerror() -> None:
    from typing import Protocol

    class Port(Protocol):
        def go(self) -> None: ...

    c = Container()
    with pytest.raises(BindingResolutionError):
        c.make(Port)
