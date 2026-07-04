"""Fast console: Typer + LazyGroup, fast-path startup, banner, built-ins."""

from __future__ import annotations

import subprocess
import sys


def _run(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "arvel.console", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )


def test_version_fast_path() -> None:
    import arvel

    proc = _run("--version")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == arvel.__version__


def test_version_imports_no_typer_or_rich() -> None:
    # answering --version must import neither Typer nor rich/click
    proc = subprocess.run(
        [sys.executable, "-X", "importtime", "-m", "arvel.console", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    trace = proc.stderr
    for lib in ("typer", "rich", "click", "litestar", "sqlalchemy"):
        assert f" {lib}" not in trace, f"--version eagerly imported {lib!r}"


def test_about_runs_and_shows_version() -> None:
    import arvel

    proc = _run("about")
    assert proc.returncode == 0, proc.stderr
    assert arvel.__version__ in proc.stdout


def test_extras_lists_extras() -> None:
    proc = _run("extras")
    assert proc.returncode == 0, proc.stderr
    assert "postgres" in proc.stdout


def test_new_command_surface(tmp_path: object) -> None:
    proc = _run("new", "demo", "--package", cwd=str(tmp_path))  # tmp cwd: scaffolding writes files
    assert proc.returncode == 0, proc.stderr
    assert "demo" in proc.stdout


def test_lazygroup_lists_builtins_without_importing_them() -> None:
    import typer

    from arvel.console import build_cli
    from arvel.console.lazy import LazyGroup

    app = build_cli()
    group = typer.main.get_command(app)
    assert isinstance(group, LazyGroup)
    assert {"about", "extras", "new", "down", "up"} <= set(LazyGroup.commands_manifest)
