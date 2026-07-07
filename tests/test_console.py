"""Fast console: Typer + LazyGroup, fast-path startup, banner, built-ins."""

from __future__ import annotations

import runpy
import subprocess
import sys

import pytest


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


def test_dunder_main_module_is_a_noop_import_when_not_run_as_main() -> None:
    sys.modules.pop("arvel.console.__main__", None)  # force a fresh, real import
    import arvel.console.__main__ as dunder_main  # __name__ != "__main__": no CLI invocation

    assert hasattr(dunder_main, "main")


def test_dunder_main_runs_the_cli_and_exits_zero_on_help(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # exercises the real `python -m arvel.console` entry point (the `__main__.py` guard) —
    # run in-process via runpy so it's the actual production code path, not a subprocess
    # coverage can't see.
    monkeypatch.setattr(sys, "argv", ["arvel.console", "--help"])
    sys.modules.pop("arvel.console.__main__", None)  # force a fresh run, not a cached module
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("arvel.console.__main__", run_name="__main__")
    assert exc.value.code == 0
    assert "Usage" in capsys.readouterr().out


def test_lazygroup_lists_builtins_without_importing_them() -> None:
    import typer

    from arvel.console import build_cli
    from arvel.console.lazy import LazyGroup

    app = build_cli()
    group = typer.main.get_command(app)
    assert isinstance(group, LazyGroup)
    assert {"about", "extras", "new", "down", "up"} <= set(LazyGroup.commands_manifest)
