"""Additional coverage for arvel.support.annotations fallback paths."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from arvel.support.annotations import resolve_annotations


def test_function_with_return_annotation_resolved() -> None:
    def f() -> int:
        return 1

    out = resolve_annotations(f)
    assert out["return"] is int


def test_function_with_no_annotations_returns_empty_dict() -> None:
    def f(a, b):  # noqa: ANN202  # pyright: ignore[reportMissingParameterType, reportUnknownParameterType]  # intentionally untyped fixture for resolve_annotations
        # Deliberately un-annotated to test resolve_annotations against a def
        # that has no signature info at all. The `a + b` expression is genuinely
        # unknown to pyright; that's the point of the fixture.
        return a + b  # pyright: ignore[reportUnknownVariableType]

    out = resolve_annotations(f)  # pyright: ignore[reportUnknownArgumentType]
    assert out == {}


def test_class_with_no_annotations() -> None:
    class C:
        pass

    out = resolve_annotations(C)
    assert out == {}


def test_class_with_unresolvable_annotation_falls_back_to_string() -> None:
    namespace: dict[str, object] = {}
    exec(  # noqa: S102 — dynamic class with bad annotation, for fallback test
        "class Sample:\n    a: 'UnresolvableXYZ'\n    b: int\n",
        namespace,
    )
    cls = cast("type", namespace["Sample"])
    out = resolve_annotations(cls)
    assert out["a"] == "UnresolvableXYZ"
    assert out["b"] is int


def test_function_with_unresolvable_return_falls_back_to_string() -> None:
    namespace: dict[str, object] = {}
    exec(  # noqa: S102 — dynamic, unresolvable return annotation
        "def f() -> 'NopeT':\n    pass\n",
        namespace,
    )
    fn = cast("Callable[..., Any]", namespace["f"])
    out = resolve_annotations(fn)
    assert out["return"] == "NopeT"


def test_extra_namespace_resolves_forward_ref() -> None:
    class Target:
        pass

    namespace: dict[str, object] = {}
    exec(  # noqa: S102
        "def f(x: 'Target') -> None: pass\n",
        namespace,
    )
    fn = cast("Callable[..., Any]", namespace["f"])
    out = resolve_annotations(fn, extra_namespace={"Target": Target})
    assert out["x"] is Target
