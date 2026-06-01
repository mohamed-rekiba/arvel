"""Forbidden-import architecture test.

`arvel.http.*` MUST NOT import `arvel.database.*` (and vice versa), except the
single sanctioned exemption documented in writing.
`arvel.container.*` MUST NOT import either.

This test walks every Python source file under each package and inspects its
import statements.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import arvel

PACKAGE_ROOT = Path(arvel.__file__).resolve().parent

# exactly one HTTP module is allowed to reach into arvel.database.
ALLOWED_HTTP_TO_DATABASE_IMPORTS: dict[str, set[str]] = {
    "arvel.http.middleware.database_transaction": {
        "arvel.database",
        "sqlalchemy.ext.asyncio",
    },
}


def _iter_modules(package_dir: Path) -> Iterator[tuple[str, Path]]:
    """Yield (dotted-module-name, file path) for every .py file under package_dir."""
    for path in package_dir.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(PACKAGE_ROOT.parent).with_suffix("")
        dotted = ".".join(rel.parts)
        dotted = dotted.removesuffix(".__init__")
        yield dotted, path


def _imports_in(path: Path) -> set[str]:
    """Return the set of fully-qualified module names imported by `path`."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.add(node.module)
    return imports


def _imports_target(imports: set[str], target_prefix: str) -> set[str]:
    """Return the subset of imports that target (or descend into) target_prefix."""
    return {imp for imp in imports if imp == target_prefix or imp.startswith(target_prefix + ".")}


def test_http_does_not_import_database() -> None:
    """`arvel.http.*` must not import `arvel.database.*`, except for the exempted module."""
    http_dir = PACKAGE_ROOT / "http"
    violations: list[str] = []
    for module, path in _iter_modules(http_dir):
        if module in ALLOWED_HTTP_TO_DATABASE_IMPORTS:
            continue
        hits = _imports_target(_imports_in(path), "arvel.database")
        if hits:
            violations.append(f"{module} imports {sorted(hits)}")
    assert not violations, (
        "Forbidden http→database imports (ADR-016 exempts only "
        f"{sorted(ALLOWED_HTTP_TO_DATABASE_IMPORTS)}):\n  " + "\n  ".join(violations)
    )


def test_database_does_not_import_http() -> None:
    """`arvel.database.*` must not import `arvel.http.*` (no exemption in this direction)."""
    db_dir = PACKAGE_ROOT / "database"
    if not db_dir.exists():
        # During QA-Pre RED phase, arvel.database may not exist yet — that's
        # implicitly fine (no violations possible). Once execution lands the
        # package, this test must pass.
        return
    violations: list[str] = []
    for module, path in _iter_modules(db_dir):
        hits = _imports_target(_imports_in(path), "arvel.http")
        if hits:
            violations.append(f"{module} imports {sorted(hits)}")
    assert not violations, "Forbidden database→http imports:\n  " + "\n  ".join(violations)


def test_container_does_not_import_either() -> None:
    """`arvel.container.*` must not import `arvel.database.*` or `arvel.http.*`."""
    container_dir = PACKAGE_ROOT / "container"
    violations: list[str] = []
    for module, path in _iter_modules(container_dir):
        imports = _imports_in(path)
        bad = _imports_target(imports, "arvel.database") | _imports_target(imports, "arvel.http")
        if bad:
            violations.append(f"{module} imports {sorted(bad)}")
    assert not violations, "Forbidden container imports:\n  " + "\n  ".join(violations)
