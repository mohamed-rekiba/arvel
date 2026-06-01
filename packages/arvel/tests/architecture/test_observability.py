"""Architecture test — no direct structlog.get_logger() calls in framework internals."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


def _find_structlog_get_logger_calls(path: Path) -> list[str]:
    violations: list[str] = []
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError, UnicodeDecodeError:
        return violations

    violations.extend(
        f"{path}:{node.lineno}"
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get_logger"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "structlog"
        )
    )
    return violations


def test_no_direct_structlog_get_logger_in_src() -> None:
    """After , framework internals must use Log, not structlog.get_logger()."""
    spec = importlib.util.find_spec("arvel")
    assert spec is not None, "arvel package not found on sys.path"
    assert spec.submodule_search_locations is not None

    src_root = Path(next(iter(spec.submodule_search_locations)))
    all_violations: list[str] = []
    for py_file in src_root.rglob("*.py"):
        all_violations.extend(_find_structlog_get_logger_calls(py_file))

    assert not all_violations, (
        "Direct structlog.get_logger() calls found in framework internals.\n"
        "Use from arvel.facades import Log instead:\n" + "\n".join(f"  {v}" for v in all_violations)
    )
