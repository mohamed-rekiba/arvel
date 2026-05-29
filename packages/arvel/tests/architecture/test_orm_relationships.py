"""SQLAlchemy relationship typing guardrail (lesson L5 from SQLModel research).

Every ORM ``relationship(...)`` declaration in the framework source MUST carry
a ``Mapped[...]`` annotation::

    # BAD — the SQLModel shape; pyright/mypy see ``Any`` for ``user.posts``
    posts: list["Post"] = relationship(back_populates="author")

    # GOOD — SQLAlchemy typed declarative
    posts: Mapped[list["Post"]] = relationship(back_populates="author")

This test walks every Python file under ``arvel.*`` and fails if any
relationship-bound class attribute is missing the ``Mapped[...]`` envelope.

Why a runtime AST test (not a mypy/pyright assertion)? The bug it catches is
silent — the bad shape compiles, runs, and only fails at type-check time. A
test makes it visible in the same CI lane as the rest of the suite, and
catches the regression even in modules pyright temporarily skips.
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
            if _annotation_uses_mapped(stmt.annotation):
                continue
            target = ast.unparse(stmt.target) if hasattr(ast, "unparse") else "<?>"
            bad.append(f"{path}:{stmt.lineno} {node.name}.{target}")
    return bad


def test_framework_relationships_use_mapped_annotation() -> None:
    """No ``relationship(...)`` in ``arvel.*`` may sit on a bare annotation."""
    violations: list[str] = []
    for path in _iter_python_files(PACKAGE_ROOT):
        violations.extend(_violations_in(path))

    assert not violations, (
        "SQLAlchemy typed relationships require ``Mapped[...]``:\n  " + "\n  ".join(violations)
    )


def test_make_model_stub_uses_mapped_annotation() -> None:
    """The ``make:model`` generator stub must teach the typed shape.

    Reads the source file directly rather than the module's private template
    constant — keeps the test stable across template renames and avoids
    pyright's ``reportPrivateUsage`` for cross-module ``_TEMPLATE`` access.

    Also verifies the stub uses :mod:`arvel.database.columns` helpers (the L2
    lesson from research 002) so newly-generated models start from the typed,
    helper-based shape instead of raw ``mapped_column(...)`` calls.
    """
    from arvel.console.commands import make_model

    module_path = make_model.__file__
    assert module_path is not None, "make_model module must be loaded from a file"
    source = Path(module_path).read_text(encoding="utf-8")
    assert "Mapped[" in source, "make:model stub must use ``Mapped[...]`` typing"
    assert "from sqlalchemy.orm import Mapped" in source, (
        "make:model stub must import ``Mapped`` so users start from the typed shape"
    )
    assert "from arvel.database import" in source and "id_" in source and "string" in source, (
        "make:model stub must import + use ``arvel.database.columns`` helpers "
        "(``id_``, ``string``, …) — not raw ``mapped_column(...)`` calls"
    )
