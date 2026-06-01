""": no ``sys.path`` mutation during file loading.

Snapshots ``sys.path`` around every public entry point that triggers file
loading. The invariant survives across Red → Green: today every call
raises ``NotImplementedError`` before any mutation could happen; once
Stage 3b implements the bodies, the loader's load-time assertion (per
Loader contract also runs, and these tests verify it from the outside.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from arvel.application._loader import NAMESPACE_PREFIX, load_module_from_path


def _assert_unchanged(snapshot: list[str]) -> None:
    assert sys.path == snapshot, "sys.path was mutated by a loader call (NFR-004-004 violation)"


def test_load_module_from_path_does_not_mutate_sys_path(tmp_path: Path) -> None:
    path = tmp_path / "noop.py"
    path.write_text("X = 1\n")
    module_name = f"{NAMESPACE_PREFIX}.tests.sp_a"
    snapshot = list(sys.path)

    try:
        load_module_from_path(path, module_name)
    finally:
        sys.modules.pop(module_name, None)

    _assert_unchanged(snapshot)


def test_load_module_from_path_does_not_mutate_sys_path_even_when_loaded_file_tries(
    tmp_path: Path,
) -> None:
    """If user code appends to sys.path inside the module, the loader detects + raises."""
    path = tmp_path / "evil.py"
    path.write_text("import sys\nsys.path.append('/totally-evil')\n")
    module_name = f"{NAMESPACE_PREFIX}.tests.sp_evil"
    snapshot = list(sys.path)

    try:
        with pytest.raises((RuntimeError, AssertionError)):
            load_module_from_path(path, module_name)
    finally:
        sys.modules.pop(module_name, None)
        # Defensive cleanup if the loader did NOT catch the mutation.
        if "/totally-evil" in sys.path:
            sys.path.remove("/totally-evil")

    _assert_unchanged(snapshot)


def test_with_config_dir_create_does_not_mutate_sys_path(tmp_path: Path) -> None:
    from arvel import Application

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "database.py").write_text('DEFAULT = "sqlite"\n')
    snapshot = list(sys.path)

    Application.configure(tmp_path).with_environment("testing").with_config_dir(config_dir).create()

    _assert_unchanged(snapshot)


def test_with_routing_create_does_not_mutate_sys_path(tmp_path: Path) -> None:
    """A registered web route loads at register() time without mutating sys.path."""
    pytest.importorskip("fastapi")
    from arvel import Application, HttpServiceProvider

    routes_dir = tmp_path / "routes"
    routes_dir.mkdir()
    (routes_dir / "web.py").write_text(
        "from arvel import Route\n"
        "\n"
        "@Route.get('/syspath-check')\n"
        "async def handler() -> dict[str, bool]:\n"
        "    return {'ok': True}\n",
    )
    snapshot = list(sys.path)

    Application.configure(tmp_path).with_environment("testing").with_providers(
        [HttpServiceProvider]
    ).with_routing(web=routes_dir / "web.py").create()

    _assert_unchanged(snapshot)


def test_with_providers_path_create_does_not_mutate_sys_path(tmp_path: Path) -> None:
    from arvel import Application

    bootstrap_dir = tmp_path / "bootstrap"
    bootstrap_dir.mkdir()
    (bootstrap_dir / "providers.py").write_text("providers: list[type] = []\n")
    snapshot = list(sys.path)

    Application.configure(tmp_path).with_environment("testing").with_providers(
        bootstrap_dir / "providers.py"
    ).create()

    _assert_unchanged(snapshot)
