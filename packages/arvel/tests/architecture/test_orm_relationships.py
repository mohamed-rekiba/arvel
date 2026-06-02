"""SQLAlchemy relationship annotation guardrail.

Every ORM ``relationship(...)`` declaration in the framework source uses the
**clean** annotation — no wrapper envelope::

    # Arvel's relationship() returns Any, so the plain annotation drives the
    # type and the metaclass wraps it at build time, like the column helpers.
    posts: list["Post"] = relationship(back_populates="author")

A relationship attribute that still carries the SQLAlchemy wrapper fails this
guardrail.

This mirrors the column guardrail in the kit's ``test_056`` (no ``Mapped[T]``
on the left side). It walks every Python file under ``arvel.*`` and fails if a
relationship-bound class attribute still carries the ``Mapped[...]`` wrapper.

Why a runtime AST test (not a mypy/pyright assertion)? It keeps the convention
visible in the same CI lane as the rest of the suite, and catches a regression
even in modules pyright temporarily skips.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import arvel

PACKAGE_ROOT = Path(arvel.__file__).resolve().parent


def _iter_python_files(root: Path) -> Iterator[Path]:
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path


def _is_relationship_call(node: ast.expr | None) -> bool:
    """Return True when ``node`` calls something named ``relationship`` or a SQLA helper."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    # Plain ``relationship(...)``.
    if isinstance(func, ast.Name) and func.id in {"relationship", "_relationship"}:
        return True
    # ``orm.relationship(...)`` or ``sqla.relationship(...)``.
    return isinstance(func, ast.Attribute) and func.attr in {
        "relationship",
        "_relationship",
    }


def _annotation_uses_mapped(annotation: ast.expr | None) -> bool:
    """Return True when ``annotation`` is a ``Mapped[...]`` subscript."""
    if annotation is None:
        return False
    if isinstance(annotation, ast.Subscript):
        target = annotation.value
        if isinstance(target, ast.Name) and target.id == "Mapped":
            return True
        if isinstance(target, ast.Attribute) and target.attr == "Mapped":
            return True
    # String forms like ``"Mapped[list[Post]]"``.
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        return annotation.value.lstrip().startswith("Mapped[")
    return False


def _violations_in(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    bad: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.AnnAssign):
                continue
            if not _is_relationship_call(stmt.value):
                continue
            if not _annotation_uses_mapped(stmt.annotation):
                continue
            target = ast.unparse(stmt.target) if hasattr(ast, "unparse") else "<?>"
            bad.append(f"{path}:{stmt.lineno} {node.name}.{target}")
    return bad


def test_framework_relationships_use_clean_annotation() -> None:
    """No ``relationship(...)`` in ``arvel.*`` may carry a ``Mapped[...]`` wrapper."""
    violations: list[str] = []
    for path in _iter_python_files(PACKAGE_ROOT):
        violations.extend(_violations_in(path))

    assert not violations, (
        "Relationships use the clean annotation (the metaclass wraps it); "
        "drop the ``Mapped[...]`` wrapper:\n  " + "\n  ".join(violations)
    )


def test_make_model_stub_uses_bare_column_helpers() -> None:
    """The ``make:model`` generator stub must teach the bare helper shape.

    Reads the source file directly rather than the module's private template
    constant — keeps the test stable across template renames and avoids
    pyright's ``reportPrivateUsage`` for cross-module ``_TEMPLATE`` access.

    Columns use the plain annotation (``id: int = id_()``) — the model
    metaclass wraps it in ``Mapped[int]`` at runtime — together with the
    helpers from :mod:`arvel.database.columns`, not raw ``mapped_column(...)``
    calls. Relationships are clean too (covered by
    :func:`test_framework_relationships_use_clean_annotation`), so the stub
    never needs to import ``Mapped``.
    """
    from arvel.console.commands import make_model

    module_path = make_model.__file__
    assert module_path is not None, "make_model module must be loaded from a file"
    source = Path(module_path).read_text(encoding="utf-8")
    assert "id: int = id_()" in source, "make:model stub must use the bare column annotation"
    assert "name: str = string(255)" in source, "make:model stub must use bare helper columns"
    assert "from sqlalchemy.orm import Mapped" not in source, (
        "the column-only make:model stub must not import ``Mapped`` — "
        "the metaclass wraps the bare annotation"
    )
    assert "from arvel.database import" in source and "id_" in source and "string" in source, (
        "make:model stub must import + use ``arvel.database.columns`` helpers "
        "(``id_``, ``string``, …) — not raw ``mapped_column(...)`` calls"
    )
