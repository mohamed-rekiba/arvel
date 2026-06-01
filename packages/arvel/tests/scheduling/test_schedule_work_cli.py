"""Tests for `arvel schedule:work` Typer command."""

from __future__ import annotations

from typer.testing import CliRunner


def test_schedule_work_command_is_registered() -> None:
    from arvel.console.entrypoint import build_app

    runner = CliRunner()
    result = runner.invoke(build_app(), ["schedule:work", "--help"])

    assert result.exit_code == 0


def test_schedule_work_once_requires_bound_application() -> None:
    """schedule:work needs a framework Application bound to ``self.app``.

    Previously this test relied on schedule_commands silently building an empty
    Schedule when invoked, which meant the user's actual Kernel.schedule() tasks
    never ran. made the command refuse to run unless the entrypoint has
    bootstrapped a framework Application and bound it to ``self.app``.
    """
    from arvel.console.entrypoint import build_app

    runner = CliRunner()
    result = runner.invoke(build_app(), ["schedule:work", "--once", "--sleep", "0"])

    # Exits non-zero because no framework Application is bound (no
    # `bootstrap/app.py` in the test cwd). RuntimeError → SystemExit 1 via Typer.
    assert result.exit_code != 0


def test_schedule_list_command_is_registered() -> None:
    """Per design doc — `arvel schedule:list` shows registered tasks."""
    from arvel.console.entrypoint import build_app

    runner = CliRunner()
    result = runner.invoke(build_app(), ["schedule:list", "--help"])

    assert result.exit_code == 0
