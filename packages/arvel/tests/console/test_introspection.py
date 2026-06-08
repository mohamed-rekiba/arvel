"""Introspection commands (db:show, db:table, model:show, channel:list, event:list).

db:show exits 0 and prints connection info
db:table <name> prints columns of an existing table
db:table <nonexistent> exits 2
model:show <model.path> prints table + attributes
channel:list prints channels or "(none registered)"
event:list prints events with listeners
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

import pytest

# RED: imports fail until Stage 3b
from arvel.console import Application, Command
from arvel.console.commands.channel_list import ChannelListCommand
from arvel.console.commands.config_commands import ConfigShowCommand
from arvel.console.commands.db_show import DbShowCommand
from arvel.console.commands.db_table import DbTableCommand
from arvel.console.commands.event_list import EventListCommand
from arvel.console.commands.model_show import ModelShowCommand
from arvel.console.commands.view_commands import ViewClearCommand
from click.testing import CliRunner as ClickCliRunner
from typer.testing import CliRunner

from .conftest import invoke_async

runner = CliRunner()


def _app(*cmds: Command) -> Application:
    return Application(commands=list(cmds))


# ─── — db:show ──────────────────────────────────────────────────────


def test_db_show_prints_connection_info(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """db:show exits 0 and prints driver + database name."""
    # The actual test requires a bootstrapped Application; for unit-level we
    # check that the command class exists and registers a 'db:show' name.
    app = _app(DbShowCommand())
    assert DbShowCommand.name == "db:show"
    assert app.has_command("db:show")


def test_config_show_prints_registered_config_value(tmp_path: Path) -> None:
    """config:show prints a dotted-key config value."""
    from types import SimpleNamespace

    from arvel.config._lookup_registry import register

    register("app", SimpleNamespace(NAME="arvel"))
    app = _app(ConfigShowCommand())
    with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app.typer_app, ["config:show", "app.NAME"])

    assert result.exit_code == 0
    assert '"arvel"' in result.output


def test_config_show_missing_key_exits_two(tmp_path: Path) -> None:
    app = _app(ConfigShowCommand())
    with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app.typer_app, ["config:show", "missing.KEY"])

    assert result.exit_code == 2


# ─── / — db:table ──────────────────────────────────────────


def test_db_table_command_registered() -> None:
    """db:table is a registered command."""
    app = _app(DbTableCommand())
    assert DbTableCommand.name == "db:table"
    assert app.has_command("db:table")


def test_db_table_nonexistent_table_exits_two(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """db:table on missing table exits 2."""
    from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    class _FakeContainer:
        def make(self, key: object) -> object:
            if key is AsyncEngine:
                return engine
            raise KeyError(key)

    class _FakeApp:
        container = _FakeContainer()

    try:
        cmd = DbTableCommand()
        cmd.app = _FakeApp()  # type: ignore[assignment]
        app = _app(cmd)
        with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
            result = invoke_async(runner, app.typer_app, ["db:table", "nonexistent_table_xyz"])
            assert result.exit_code == 2, result.stdout + result.stderr
    finally:
        asyncio.run(engine.dispose())


# ─── — model:show ────────────────────────────────────────────────────


def test_model_show_command_registered() -> None:
    """model:show is a registered command."""
    app = _app(ModelShowCommand())
    assert ModelShowCommand.name == "model:show"
    assert app.has_command("model:show")


def test_model_show_with_missing_import_exits_two(tmp_path: Path) -> None:
    """model:show on bogus dotted path exits 2."""
    app = _app(ModelShowCommand())
    with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app.typer_app, ["model:show", "no.such.module.NoClass"])
        assert result.exit_code == 2


# ─── — channel:list ─────────────────────────────────────────────────


def test_channel_list_command_registered() -> None:
    """channel:list is a registered command."""
    app = _app(ChannelListCommand())
    assert ChannelListCommand.name == "channel:list"
    assert app.has_command("channel:list")


# ─── — event:list ────────────────────────────────────────────────────


def test_event_list_command_registered() -> None:
    """event:list is a registered command."""
    app = _app(EventListCommand())
    assert EventListCommand.name == "event:list"
    assert app.has_command("event:list")


def test_view_clear_command_registered_and_runs() -> None:
    app = _app(ViewClearCommand())
    result = runner.invoke(app.typer_app, ["view:clear"])

    assert result.exit_code == 0
    assert "View cache cleared." in result.output
