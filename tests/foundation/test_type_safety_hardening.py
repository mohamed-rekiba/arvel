"""QA-Pre tests for Foundation hardening — WI-Arvel-001.

These tests verify the PRD acceptance criteria for type safety hardening.

FR-001: Explicit re-exports (__init__.py uses X as X)
FR-002: Type-safe Pipeline (Self returns, typed Container, no dead TypeVar)
FR-003: Type-safe Container internals (typed _Binding.factory)
FR-004: Config exception bug fix (proper tuple syntax)
FR-005: Config type safety (generic with_env_files, typed _load_python_module)
FR-006: Application bootstrap dedup (_bootstrap method exists)
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import get_type_hints

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "arvel"


# ── FR-001: Explicit re-exports ──────────────────────────────────────────


class TestExplicitReExports:
    """FR-001: __init__.py must use 'X as X' pattern for all re-exports."""

    def test_init_uses_as_pattern_for_all_exports(self) -> None:
        init_path = SRC_ROOT / "foundation" / "__init__.py"
        source = init_path.read_text()
        tree = ast.parse(source)

        imported_names: list[str] = []
        uses_as_pattern: list[bool] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imported_names.append(alias.name)
                    uses_as_pattern.append(alias.asname == alias.name)

        missing_as = [
            name for name, has_as in zip(imported_names, uses_as_pattern, strict=True) if not has_as
        ]
        assert not missing_as, f"These re-exports are missing 'X as X' pattern: {missing_as}"


# ── FR-002: Type-safe Pipeline ───────────────────────────────────────────


class TestTypeSafePipeline:
    """FR-002: Pipeline has no Any in public signatures."""

    def test_send_returns_self_type(self) -> None:
        from arvel.foundation.pipeline import Pipeline

        hints = get_type_hints(Pipeline.send, include_extras=True)
        return_type = hints.get("return")
        assert return_type is not None
        type_name = getattr(return_type, "__name__", str(return_type))
        assert type_name == "Self", f"Pipeline.send() should return Self, got {type_name}"

    def test_through_returns_self_type(self) -> None:
        from arvel.foundation.pipeline import Pipeline

        hints = get_type_hints(Pipeline.through, include_extras=True)
        return_type = hints.get("return")
        assert return_type is not None
        type_name = getattr(return_type, "__name__", str(return_type))
        assert type_name == "Self", f"Pipeline.through() should return Self, got {type_name}"

    def test_container_param_is_not_any(self) -> None:
        from arvel.foundation.pipeline import Pipeline

        raw_annotations = inspect.get_annotations(Pipeline.__init__, eval_str=False)
        container_ann = raw_annotations.get("container", "")
        ann_str = str(container_ann)
        assert "Any" not in ann_str, (
            f"Pipeline.__init__ container param should be Container | None, got {ann_str}"
        )
        assert "Container" in ann_str, (
            f"Pipeline.__init__ container param should reference Container, got {ann_str}"
        )

    def test_no_unused_typevar_import(self) -> None:
        source_path = SRC_ROOT / "foundation" / "pipeline.py"
        source = source_path.read_text()
        tree = ast.parse(source)

        has_typevar_assignment = False
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "T"
                and isinstance(node.value, ast.Call)
            ):
                func = node.value.func
                name = getattr(func, "id", getattr(func, "attr", ""))
                if name == "TypeVar":
                    has_typevar_assignment = True

        assert not has_typevar_assignment, "pipeline.py still has unused T = TypeVar('T')"

    def test_pipe_type_alias_exists(self) -> None:
        from arvel.foundation.pipeline import Pipe

        assert Pipe is not None, "Pipeline module should export a Pipe type alias"
        type_str = str(Pipe)
        assert "Callable" in type_str, f"Pipe should be a Callable alias, got {type_str}"


# ── FR-003: Type-safe Container internals ────────────────────────────────


class TestTypeSafeContainer:
    """FR-003: Container _Binding.factory is properly typed."""

    def test_binding_factory_is_not_any(self) -> None:
        from arvel.foundation.container import _Binding

        hints = get_type_hints(_Binding.__init__, include_extras=True)
        factory_type = hints.get("factory")
        assert factory_type is not None
        type_str = str(factory_type)
        assert type_str != "typing.Any | None", (
            f"_Binding.factory should be Callable[[], object] | None, got {type_str}"
        )


# ── FR-004: Config exception style ───────────────────────────────────────


class TestConfigExceptionStyle:
    """FR-004: _load_cached_root_settings catches both exception types."""

    def test_except_clause_catches_both_exceptions(self) -> None:
        source_path = SRC_ROOT / "foundation" / "config.py"
        tree = ast.parse(source_path.read_text())

        found_handler = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            exc_type = node.type
            if exc_type is None:
                continue
            if isinstance(exc_type, ast.Tuple) and len(exc_type.elts) == 2:
                names = []
                for elt in exc_type.elts:
                    if isinstance(elt, ast.Attribute):
                        names.append(f"{getattr(elt.value, 'id', '')}.{elt.attr}")
                    elif isinstance(elt, ast.Name):
                        names.append(elt.id)
                if "json.JSONDecodeError" in names and "ValidationError" in names:
                    found_handler = True
                    break

        assert found_handler, (
            "_load_cached_root_settings must catch both json.JSONDecodeError and ValidationError"
        )


# ── FR-005: Config type safety ───────────────────────────────────────────


class TestConfigTypeSafety:
    """FR-005: Config helpers return properly typed values."""

    def test_load_python_module_returns_module_type(self) -> None:
        from arvel.foundation import config

        hints = get_type_hints(config._load_python_module)
        return_type = hints.get("return")
        assert return_type is not None
        type_str = str(return_type)
        assert "ModuleType" in type_str or "types.ModuleType" in type_str or "module" in type_str, (
            f"_load_python_module should return ModuleType | None, got {type_str}"
        )


# ── FR-006: Application bootstrap dedup ──────────────────────────────────


class TestApplicationBootstrapDedup:
    """FR-006: Duplicated bootstrap logic extracted to shared method."""

    def test_bootstrap_method_exists(self) -> None:
        from arvel.foundation.application import Application

        assert hasattr(Application, "_bootstrap"), "Application should have a _bootstrap() method"

    def test_bootstrap_is_async(self) -> None:
        from arvel.foundation.application import Application

        method = getattr(Application, "_bootstrap", None)
        assert method is not None
        assert inspect.iscoroutinefunction(method), "Application._bootstrap() should be async"

    def test_create_delegates_to_bootstrap(self) -> None:
        from arvel.foundation.application import Application

        source = inspect.getsource(Application.create)
        assert "_bootstrap" in source, "Application.create() should delegate to _bootstrap()"

    def test_boot_delegates_to_bootstrap(self) -> None:
        from arvel.foundation.application import Application

        source = inspect.getsource(Application._boot)
        assert "_bootstrap" in source, "Application._boot() should delegate to _bootstrap()"
