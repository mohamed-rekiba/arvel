"""Tests for the PluginRegistry and LazyPluginGroup infrastructure."""

from __future__ import annotations

from typing import TYPE_CHECKING

import typer
from typer.testing import CliRunner

from arvel.cli.app import app
from arvel.cli.registry import PluginRegistry

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


class TestPluginRegistryBuiltins:
    """Verify the registry lists all known built-in commands."""

    def test_builtin_names_returns_sorted_list(self) -> None:
        names = PluginRegistry.builtin_names()
        assert names == sorted(names)
        assert "serve" in names
        assert "new" in names
        assert "db" in names

    def test_help_text_for_known_command(self) -> None:
        text = PluginRegistry.help_text("serve")
        assert isinstance(text, str)
        assert len(text) > 0

    def test_import_command_returns_click_command(self) -> None:
        reg = PluginRegistry()
        cmd = reg._import_command("about")
        assert cmd is not None
        assert cmd.name == "about"

    def test_import_command_caches_result(self) -> None:
        reg = PluginRegistry()
        cmd1 = reg._import_command("about")
        cmd2 = reg._import_command("about")
        assert cmd1 is cmd2

    def test_import_unknown_command_returns_none(self) -> None:
        reg = PluginRegistry()
        assert reg._import_command("nonexistent") is None


class TestPluginRegistryCallable:
    """Verify callable-based plugins (new, down, up) resolve correctly."""

    def test_new_resolves_as_callable_command(self) -> None:
        reg = PluginRegistry()
        cmd = reg._import_command("new")
        assert cmd is not None
        assert cmd.name == "new"

    def test_down_resolves_as_callable_command(self) -> None:
        reg = PluginRegistry()
        cmd = reg._import_command("down")
        assert cmd is not None
        assert cmd.name == "down"

    def test_up_resolves_as_callable_command(self) -> None:
        reg = PluginRegistry()
        cmd = reg._import_command("up")
        assert cmd is not None
        assert cmd.name == "up"


class TestPluginRegistryTyperApps:
    """Verify Typer sub-app plugins resolve as Click groups."""

    def test_db_resolves_as_group(self) -> None:
        reg = PluginRegistry()
        cmd = reg._import_command("db")
        assert cmd is not None
        assert cmd.name == "db"

    def test_make_resolves_as_group(self) -> None:
        reg = PluginRegistry()
        cmd = reg._import_command("make")
        assert cmd is not None
        assert cmd.name == "make"


class TestLazyPluginGroupIntegration:
    """Verify commands resolve via the main Typer app with LazyPluginGroup."""

    def test_help_lists_all_commands(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "serve" in result.output
        assert "new" in result.output
        assert "db" in result.output
        assert "about" in result.output

    def test_lazy_command_resolves_on_invoke(self) -> None:
        result = runner.invoke(app, ["about"])
        assert result.exit_code == 0
        assert "Arvel" in result.output

    def test_lazy_subgroup_resolves_on_invoke(self) -> None:
        result = runner.invoke(app, ["db", "--help"])
        assert result.exit_code == 0
        assert "migrate" in result.output

    def test_unknown_command_fails_gracefully(self) -> None:
        result = runner.invoke(app, ["nonexistent"])
        assert result.exit_code != 0


class TestPluginRegistryDiscoverUser:
    """Verify user command discovery from app/Console/Commands/."""

    def test_discover_user_commands_from_directory(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / "app" / "Console" / "Commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "billing.py").write_text(
            "import typer\n"
            "billing_app = typer.Typer(name='billing', help='test')\n"
            "@billing_app.command()\ndef charge():\n    print('charged')\n"
        )

        test_app = typer.Typer(name="arvel")
        reg = PluginRegistry()
        reg.discover_user_commands(test_app, base_path=tmp_path)

        group_names = [g.name for g in test_app.registered_groups]
        assert "billing" in group_names

    def test_discover_skips_nonexistent_dir(self, tmp_path: Path) -> None:
        test_app = typer.Typer(name="arvel")
        reg = PluginRegistry()
        reg.discover_user_commands(test_app, base_path=tmp_path)

    def test_discover_skips_underscored_files(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / "app" / "Console" / "Commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "__init__.py").write_text("")
        (commands_dir / "_private.py").write_text("import typer\n")

        test_app = typer.Typer(name="arvel")
        reg = PluginRegistry()
        reg.discover_user_commands(test_app, base_path=tmp_path)
        assert len(test_app.registered_groups) == 0
