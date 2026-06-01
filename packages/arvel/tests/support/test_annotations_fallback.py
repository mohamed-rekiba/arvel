"""Per-element annotation fallback — exercised when get_type_hints bails.

A single unresolvable forward ref makes typing.get_type_hints raise, which
drops resolve_annotations into its per-name eval loop. We mix a real type
with a broken string so both branches (eval-fail vs already-a-type) run.
"""

from __future__ import annotations

from typing import Any

from arvel.support.annotations import resolve_annotations

_BROKEN = "DefinitelyUndefinedForwardRef"


def test_class_fallback_keeps_broken_ref_as_string() -> None:
    class Subject:
        pass

    Subject.__annotations__ = {"good": int, "bad": _BROKEN}
    out = resolve_annotations(Subject)
    assert out["good"] is int
    assert out["bad"] == _BROKEN


def test_callable_fallback_handles_empty_and_real_and_broken() -> None:
    def handler(a: Any, b: Any, c: Any) -> Any:  # real annotations replaced below
        return None

    handler.__annotations__ = {"b": _BROKEN, "c": int, "return": float}
    out = resolve_annotations(handler)
    assert "a" not in out  # no annotation → skipped
    assert out["b"] == _BROKEN
    assert out["c"] is int
    assert out["return"] is float


def test_callable_fallback_without_return_annotation() -> None:
    def handler(b: Any) -> None:
        return None

    handler.__annotations__ = {"b": _BROKEN}
    out = resolve_annotations(handler)
    assert out["b"] == _BROKEN
    assert "return" not in out


def test_callable_fallback_return_string_kept_on_eval_failure() -> None:
    def handler(b: Any) -> None:
        return None

    # Both the param and the return are unresolvable strings; each is kept verbatim.
    handler.__annotations__ = {"b": _BROKEN, "return": _BROKEN}
    out = resolve_annotations(handler)
    assert out["return"] == _BROKEN
