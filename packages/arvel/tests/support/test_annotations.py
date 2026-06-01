"""extracted ``resolve_annotations`` lives in ``arvel.support``."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import arvel.routing
from arvel.support.annotations import resolve_annotations


def test_resolve_annotations_resolves_pep_563() -> None:
    def handler(name: str, count: int = 1) -> bool:
        return bool(name) and count > 0

    out = resolve_annotations(handler)
    assert out == {"name": str, "count": int, "return": bool}


def test_resolve_annotations_uses_caller_locals_for_closure_types() -> None:
    class Closure:
        pass

    def handler(thing: Closure) -> None:
        del thing

    out = resolve_annotations(handler, caller_locals={"Closure": Closure})
    assert out["thing"] is Closure


def test_resolve_annotations_falls_back_on_string_when_unresolvable() -> None:
    # Build a handler whose annotation references a name that exists nowhere.
    # Using exec keeps the typechecker from flagging an undefined name.
    namespace: dict[str, object] = {}
    exec(  # noqa: S102 — intentional dynamic definition
        "def handler(x: 'ThisNameDoesNotExist') -> None:\n    pass\n",
        namespace,
    )
    handler = namespace["handler"]
    out = resolve_annotations(handler)  # type: ignore[arg-type]
    assert out["x"] == "ThisNameDoesNotExist"


def test_resolve_annotations_handles_classes() -> None:
    class Sample:
        a: int
        b: str

    out = resolve_annotations(Sample)
    assert out["a"] is int
    assert out["b"] is str


def test_routing_does_not_redefine_resolve_annotations() -> None:
    """: arvel.routing reuses arvel.support.annotations — no parallel definition."""
    source_file = inspect.getsourcefile(arvel.routing)
    assert source_file is not None
    src = Path(source_file).read_text(encoding="utf-8")
    tree = ast.parse(src)
    function_defs = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_resolve_annotations"
    ]
    assert len(function_defs) == 1, "Expected exactly one shim in arvel.routing"
    # And the shim body must import from arvel.support.annotations (it's a delegating shim,
    # not a re-implementation).
    assert "from arvel.support.annotations import" in src
