"""Private file-to-module loader used by ApplicationBuilder.

Loads Python files by absolute path under namespaced module names so the
user's files never shadow stdlib or each other across multiple Arvel apps
in the same process. Asserts ``sys.path`` is unchanged before and after
each load."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

NAMESPACE_PREFIX = "_arvel_user_app"
"""Prefix for every dotted module name the loader writes into ``sys.modules``.

A leading underscore signals "framework-private namespace, do not import
from user code". The full module name is ``<NAMESPACE_PREFIX>.<subpkg>.<stem>``
(see module name conventions).
"""

# Process-level cache: (resolved_path_str, mtime) -> loaded ModuleType.
# Avoids re-parsing unchanged config files on repeated create() calls —
# common in tests and in multi-app setups. Call clear_module_cache() to
# force a fresh load (e.g., when the file is mutated during a test).
_module_cache: dict[tuple[str, float], ModuleType] = {}


class LoaderError(RuntimeError):
    """Raised when the loader cannot turn a path into a module."""


class SysPathMutationError(RuntimeError):
    """Raised when loaded code mutates ``sys.path``."""


def clear_module_cache() -> None:
    """Evict all cached modules. Useful in tests that mutate config files."""
    _module_cache.clear()


def load_module_from_path(path: Path, module_name: str) -> ModuleType:
    """Load the Python file at ``path`` as a module named ``module_name``.

    Uses ``importlib.util.spec_from_file_location`` + ``module_from_spec`` +
    ``exec_module``. Snapshots ``sys.path`` before the load and asserts it
    is unchanged after — any mutation raises ``SysPathMutationError`` and
    the partially-registered ``sys.modules`` entry is rolled back.

    ``module_name`` should be namespaced under ``NAMESPACE_PREFIX`` so the
    loaded module never collides with stdlib (e.g., a user's
    ``config/logging.py`` lands at ``_arvel_user_app.config.logging``, not
    bare ``logging``).

    Results are cached per ``(resolved_path, mtime)`` so unchanged files are
    not re-parsed on repeated ``create()`` calls. Call ``clear_module_cache()``
    to invalidate.
    """
    if not path.exists():
        raise FileNotFoundError(f"Cannot load module: file does not exist: {path}")

    cache_key = (str(path.resolve()), path.stat().st_mtime)
    if cache_key in _module_cache:
        sys.modules[module_name] = _module_cache[cache_key]
        return _module_cache[cache_key]

    sys_path_before = list(sys.path)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise LoaderError(f"Could not build module spec for {path}")

    module = importlib.util.module_from_spec(spec)
    # Register before exec so intra-package relative imports inside the
    # loaded module can resolve.
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        # Roll back the sys.modules registration on any exec failure
        # (including SystemExit / KeyboardInterrupt) so a partially-loaded
        # module doesn't poison subsequent attempts.
        sys.modules.pop(module_name, None)
        raise

    if sys.path != sys_path_before:
        # Loaded code mutated sys.path — roll back BOTH sys.modules and
        # sys.path before raising so we leave the interpreter clean.
        sys.modules.pop(module_name, None)
        sys.path[:] = sys_path_before
        raise SysPathMutationError(
            f"Module {module_name!r} loaded from {path} mutated sys.path "
            f"(NFR-004-004 violation). User code must not append/insert to sys.path.",
        )

    _module_cache[cache_key] = module
    return module


def discover_config_files(directory: Path) -> list[Path]:
    """Return a sorted list of ``.py`` files in ``directory``.

    Rules:
    - Non-recursive (subdirectories are NOT walked).
    - Files prefixed with ``_`` are excluded.
    - Non-``.py`` files are excluded.

    Raises ``FileNotFoundError`` if ``directory`` does not exist.
    """
    if not directory.exists():
        raise FileNotFoundError(f"Config directory does not exist: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"Config path is not a directory: {directory}")

    return sorted(
        entry
        for entry in directory.iterdir()
        if entry.is_file() and entry.suffix == ".py" and not entry.name.startswith("_")
    )
