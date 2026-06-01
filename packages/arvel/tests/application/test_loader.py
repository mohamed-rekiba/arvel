"""/009/010 + : file-to-module loader contract.

the private ``arvel.application._loader`` module that backs the
three new ``ApplicationBuilder`` methods.
(``importlib.util.spec_from_file_location`` + namespaced module names +
``sys.path``-invariant assertion at load time).
"""

from __future__ import annotations

import logging as stdlib_logging
import sys
from pathlib import Path

import pytest
from arvel.application._loader import (
    NAMESPACE_PREFIX,
    LoaderError,
    SysPathMutationError,
    discover_config_files,
    load_module_from_path,
)


def test_namespace_prefix_is_framework_private() -> None:
    """Underscore prefix signals 'do not import from user code'."""
    assert NAMESPACE_PREFIX.startswith("_")
    assert NAMESPACE_PREFIX == "_arvel_user_app"


def test_loader_errors_are_subclasses_of_runtime_error() -> None:
    """Both loader errors must be RuntimeError subclasses for uniform catching."""
    assert issubclass(LoaderError, RuntimeError)
    assert issubclass(SysPathMutationError, RuntimeError)


def test_load_module_from_path_returns_module_with_expected_name(tmp_path: Path) -> None:
    """Loaded module has the requested namespaced name and exposes its top-level attrs."""
    path = tmp_path / "sample.py"
    path.write_text('GREETING = "hello"\n')

    module = load_module_from_path(path, f"{NAMESPACE_PREFIX}.sample")

    assert module.__name__ == f"{NAMESPACE_PREFIX}.sample"
    assert module.GREETING == "hello"


def test_load_module_from_path_registers_in_sys_modules(tmp_path: Path) -> None:
    """Loaded module is reachable through ``sys.modules`` under its namespaced name."""
    path = tmp_path / "marker.py"
    path.write_text("VALUE = 42\n")
    module_name = f"{NAMESPACE_PREFIX}.tests.marker_a"

    try:
        load_module_from_path(path, module_name)
        assert module_name in sys.modules
        assert sys.modules[module_name].VALUE == 42
    finally:
        sys.modules.pop(module_name, None)


def test_load_module_from_path_namespaced_logging_does_not_shadow_stdlib(tmp_path: Path) -> None:
    """User's ``config/logging.py`` MUST NOT replace stdlib ``logging`` in sys.modules.

    This is the core mitigation in § Conventions: namespaced module
    names prevent stdlib shadowing.
    """
    path = tmp_path / "logging.py"
    path.write_text('LEVEL = "DEBUG"\n')
    module_name = f"{NAMESPACE_PREFIX}.config.logging"

    try:
        load_module_from_path(path, module_name)
        # Stdlib logging is still intact.
        assert sys.modules["logging"] is stdlib_logging
        # User's logging module is at the namespaced key.
        assert sys.modules[module_name].LEVEL == "DEBUG"
    finally:
        sys.modules.pop(module_name, None)


def test_load_module_from_path_missing_file_raises_loader_error(tmp_path: Path) -> None:
    """A non-existent path raises LoaderError (or its FileNotFoundError subclass)."""
    missing = tmp_path / "does_not_exist.py"

    with pytest.raises((LoaderError, FileNotFoundError)):
        load_module_from_path(missing, f"{NAMESPACE_PREFIX}.missing")


def test_load_module_from_path_syntax_error_propagates(tmp_path: Path) -> None:
    """Loading a file with a syntax error surfaces the SyntaxError."""
    path = tmp_path / "broken.py"
    path.write_text("def oops(\n")  # Intentionally broken.

    with pytest.raises(SyntaxError):
        load_module_from_path(path, f"{NAMESPACE_PREFIX}.broken")


def test_load_module_from_path_rolls_back_sys_modules_on_exception(tmp_path: Path) -> None:
    """If the loaded module raises at exec time, sys.modules is rolled back."""
    path = tmp_path / "raises.py"
    path.write_text('raise RuntimeError("nope")\n')
    module_name = f"{NAMESPACE_PREFIX}.tests.raises_a"

    with pytest.raises(RuntimeError):
        load_module_from_path(path, module_name)

    assert module_name not in sys.modules


def test_discover_config_files_returns_sorted_non_underscore_py_files(tmp_path: Path) -> None:
    """Discovery is non-recursive, excludes _-prefixed and non-.py files, sorted."""
    (tmp_path / "app.py").touch()
    (tmp_path / "database.py").touch()
    (tmp_path / "logging.py").touch()
    (tmp_path / "_private.py").touch()
    (tmp_path / "README.md").touch()
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "deeper.py").touch()

    found = discover_config_files(tmp_path)

    assert [p.name for p in found] == ["app.py", "database.py", "logging.py"]


def test_discover_config_files_missing_directory_raises(tmp_path: Path) -> None:
    missing = tmp_path / "no_such_dir"

    with pytest.raises(FileNotFoundError):
        discover_config_files(missing)


def test_discover_config_files_empty_directory_returns_empty_list(tmp_path: Path) -> None:
    found = discover_config_files(tmp_path)

    assert found == []


def test_discover_config_files_path_is_a_file_raises(tmp_path: Path) -> None:
    a_file = tmp_path / "app.py"
    a_file.touch()

    with pytest.raises(NotADirectoryError):
        discover_config_files(a_file)


def test_load_module_unsupported_extension_raises_loader_error(tmp_path: Path) -> None:
    """A path with no importable loader (e.g. ``.txt``) raises LoaderError."""
    path = tmp_path / "data.txt"
    path.write_text("not python\n")

    with pytest.raises(LoaderError):
        load_module_from_path(path, f"{NAMESPACE_PREFIX}.tests.data_txt")


def test_load_module_caches_and_clear_forces_reload(tmp_path: Path) -> None:
    """Unchanged (path, mtime) is served from cache; clear_module_cache reloads."""
    from arvel.application import _loader

    path = tmp_path / "cached.py"
    path.write_text("X = 1\n")
    name = f"{NAMESPACE_PREFIX}.tests.cache_clear"

    try:
        first = load_module_from_path(path, name)
        # Same (path, mtime) -> cache hit returns the identical object.
        assert load_module_from_path(path, name) is first

        _loader.clear_module_cache()
        assert load_module_from_path(path, name) is not first
    finally:
        sys.modules.pop(name, None)
        _loader.clear_module_cache()
