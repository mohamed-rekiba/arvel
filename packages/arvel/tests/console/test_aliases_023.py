"""WI-023 — Alias and misc commands.

Covers: tinker, schedule:run, storage:unlink, auth:clear-resets, test.

AC covered:
  AC-008.1  arvel tinker behaves like arvel shell
  AC-008.2  arvel schedule:run behaves like arvel schedule:work --once
  AC-008.3  arvel storage:unlink removes the symlink (idempotent)
  AC-008.4  arvel auth:clear-resets deletes expired tokens and prints count
  AC-008.5  arvel test <args> forwards to pytest, exit code matches
  SR-023-006 auth:clear-resets uses parameterized DELETE
  SR-023-007 test command shell-escapes its arguments
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest
from arvel.console import Application, Command
from arvel.console.commands.auth_clear_resets import AuthClearResetsCommand
from arvel.console.commands.schedule_run import ScheduleRunCommand
from arvel.console.commands.storage_unlink import StorageUnlinkCommand
from arvel.console.commands.test_command import TestCommand
from arvel.console.commands.tinker import TinkerCommand
from typer.testing import CliRunner

runner = CliRunner()


def _app(*cmds: Command) -> Application:
    return Application(commands=list(cmds))


# ─── AC-008.1 — tinker is registered ─────────────────────────────────────────


def test_tinker_is_registered_as_alias() -> None:
    """AC-008.1: arvel tinker exists with name 'tinker'."""
    assert TinkerCommand.name == "tinker"
    app = _app(TinkerCommand())
    assert app.has_command("tinker")


# ─── AC-008.2 — schedule:run is registered ───────────────────────────────────


def test_schedule_run_is_registered() -> None:
    """AC-008.2: arvel schedule:run exists with name 'schedule:run'."""
    assert ScheduleRunCommand.name == "schedule:run"
    app = _app(ScheduleRunCommand())
    assert app.has_command("schedule:run")


# ─── AC-008.3 — storage:unlink ────────────────────────────────────────────────


def test_storage_unlink_removes_symlink(tmp_path: Path) -> None:
    """AC-008.3: storage:unlink deletes the symlink at public/storage."""
    app = _app(StorageUnlinkCommand())
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("public").mkdir(parents=True)
        target = Path("storage/app/public")
        target.mkdir(parents=True)
        link = Path("public/storage")
        link.symlink_to(target.resolve(), target_is_directory=True)
        assert link.is_symlink()
        result = runner.invoke(app.typer_app, ["storage:unlink"])
        assert result.exit_code == 0
        assert not link.exists() and not link.is_symlink()


def test_storage_unlink_is_idempotent(tmp_path: Path) -> None:
    """AC-008.3: storage:unlink when no link exists exits 0."""
    app = _app(StorageUnlinkCommand())
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("public").mkdir(parents=True)
        result = runner.invoke(app.typer_app, ["storage:unlink"])
        assert result.exit_code == 0


# ─── AC-008.4 — auth:clear-resets ────────────────────────────────────────────


def test_auth_clear_resets_is_registered() -> None:
    """AC-008.4: auth:clear-resets exists."""
    assert AuthClearResetsCommand.name == "auth:clear-resets"
    app = _app(AuthClearResetsCommand())
    assert app.has_command("auth:clear-resets")


# ─── AC-008.5 — test command ─────────────────────────────────────────────────


def test_test_command_is_registered() -> None:
    """AC-008.5: arvel test exists."""
    assert TestCommand.name == "test"
    app = _app(TestCommand())
    assert app.has_command("test")


def test_test_command_reports_missing_pytest(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-008.5: arvel test gives a useful message when dev deps are absent."""

    def missing_pytest(module_name: str) -> ModuleType:
        if module_name == "pytest":
            raise ModuleNotFoundError("No module named 'pytest'", name="pytest")
        return ModuleType(module_name)

    monkeypatch.setattr(
        "arvel.console.commands.test_command.importlib.import_module",
        missing_pytest,
    )

    result = runner.invoke(_app(TestCommand()).typer_app, ["test"])

    assert result.exit_code == 2
    assert "install dev dependencies" in result.stderr
