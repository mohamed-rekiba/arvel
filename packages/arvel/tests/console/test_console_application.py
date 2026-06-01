"""S-005-01 / S-005-02 — CLI binary + plugin discovery.

-001-01 arvel --help exits 0
-001-02 command names listed in help output
-002-01 plugin commands discovered via arvel.commands entry-point group
-002-02 name collision logs warning and last-registered wins
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock, patch

# RED: arvel.console does not exist yet → ImportError is the expected failure
from arvel.console import Application, Command, Context
from arvel.console._loader import discover_commands
from typer.testing import CliRunner

# ─── Minimal concrete Command for test doubles ───────────────────────────────


class _HelloCommand(Command):
    name = "hello"
    help = "Say hello"

    def handle(self, ctx: Context) -> int:
        ctx.info("hello")
        return 0


class _WorldCommand(Command):
    name = "world"
    help = "Say world"

    def handle(self, ctx: Context) -> int:
        ctx.info("world")
        return 0


class _CollisionCommand(Command):
    name = "hello"  # same name as _HelloCommand → collision
    help = "Collision"

    def handle(self, ctx: Context) -> int:
        ctx.info("collision")
        return 0


# ─── -001-01: arvel --help exits 0 ─────────────────────────────────────


def test_application_help_exits_zero() -> None:
    """-001-01: --help must exit with code 0."""
    runner = CliRunner()
    app = Application(commands=[_HelloCommand()])
    result = runner.invoke(app.typer_app, ["--help"])
    assert result.exit_code == 0


# ─── -001-02: registered command names appear in --help ────────────────


def test_application_help_lists_command_names() -> None:
    """-001-02: every registered command name appears in --help output."""
    runner = CliRunner()
    app = Application(commands=[_HelloCommand(), _WorldCommand()])
    result = runner.invoke(app.typer_app, ["--help"])
    assert "hello" in result.output
    assert "world" in result.output


def test_application_help_groups_make_commands() -> None:
    """-001-02: make:* commands listed under 'make' section."""

    class _MakeCtrl(Command):
        name = "make:controller"
        help = "Generate a controller"

        def handle(self, ctx: Context) -> int:
            return 0

    runner = CliRunner()
    app = Application(commands=[_MakeCtrl()])
    result = runner.invoke(app.typer_app, ["--help"])
    assert "make:controller" in result.output


# ─── -002-01: entry-point discovery ────────────────────────────────────


def test_discover_commands_returns_registered_commands(monkeypatch: Any) -> None:
    """-002-01: discover_commands finds commands from arvel.commands group."""
    fake_ep = MagicMock()
    fake_ep.load.return_value = _HelloCommand

    with patch(
        "arvel.console._loader.importlib.metadata.entry_points",
        return_value=[fake_ep],
    ):
        commands = discover_commands()

    assert any(isinstance(c, _HelloCommand) for c in commands)


def test_discover_commands_instantiates_each_class(monkeypatch: Any) -> None:
    """-002-01: each discovered class is instantiated exactly once."""
    instantiation_count = 0

    class _CountedCommand(Command):
        name = "counted"
        help = "Count me"

        def __init__(self) -> None:
            nonlocal instantiation_count
            instantiation_count += 1

        def handle(self, ctx: Context) -> int:
            return 0

    fake_ep = MagicMock()
    fake_ep.load.return_value = _CountedCommand

    with patch(
        "arvel.console._loader.importlib.metadata.entry_points",
        return_value=[fake_ep],
    ):
        discover_commands()

    assert instantiation_count == 1


# ─── -002-02: name collision → warning + last wins ─────────────────────


def test_application_warns_on_name_collision(caplog: Any) -> None:
    """-002-02: duplicate command names log a warning."""
    with caplog.at_level(logging.WARNING, logger="arvel.console"):
        Application(commands=[_HelloCommand(), _CollisionCommand()])

    assert any("hello" in record.message for record in caplog.records)


def test_application_last_registered_wins_on_collision() -> None:
    """-002-02: last-registered command wins when names collide."""
    runner = CliRunner()
    app = Application(commands=[_HelloCommand(), _CollisionCommand()])
    result = runner.invoke(app.typer_app, ["hello"])
    assert "collision" in result.output


# ─── Application.run() ───────────────────────────────────────────────────────


def test_application_run_dispatches_to_command() -> None:
    """Application.run invokes the matched command's handle."""
    runner = CliRunner()
    app = Application(commands=[_HelloCommand()])
    result = runner.invoke(app.typer_app, ["hello"])
    assert result.exit_code == 0
    assert "hello" in result.output


def test_application_run_returns_nonzero_on_handle_failure() -> None:
    """Application propagates non-zero return value from handle."""

    class _FailCmd(Command):
        name = "fail"
        help = "Always fails"

        def handle(self, ctx: Context) -> int:
            return 1

    runner = CliRunner()
    app = Application(commands=[_FailCmd()])
    result = runner.invoke(app.typer_app, ["fail"])
    assert result.exit_code != 0
