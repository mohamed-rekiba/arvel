"""Tests for module command auto-discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING

import typer
from typer.testing import CliRunner

from arvel.cli.registry import PluginRegistry

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


class TestModuleCommandDiscovery:
    def test_discovers_module_commands(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / "app" / "Console" / "Commands"
        commands_dir.mkdir(parents=True)

        commands_file = commands_dir / "billing.py"
        commands_file.write_text(
            "import typer\n"
            "billing_app = typer.Typer(name='billing', help='Billing commands.')\n"
            "@billing_app.command()\n"
            "def invoice() -> None:\n"
            "    typer.echo('Invoice generated')\n"
        )

        test_app = typer.Typer(name="arvel", no_args_is_help=True)
        reg = PluginRegistry()
        reg.discover_user_commands(test_app, base_path=tmp_path)

        group_names = [g.name for g in test_app.registered_groups]
        assert "billing" in group_names

    def test_skips_modules_without_commands(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / "app" / "Console" / "Commands" / "users"
        commands_dir.mkdir(parents=True)
        (commands_dir / "__init__.py").write_text("")

        test_app = typer.Typer(name="arvel", no_args_is_help=True)
        reg = PluginRegistry()
        reg.discover_user_commands(test_app, base_path=tmp_path)

    def test_skips_nonexistent_modules_dir(self, tmp_path: Path) -> None:
        test_app = typer.Typer(name="arvel", no_args_is_help=True)
        reg = PluginRegistry()
        reg.discover_user_commands(test_app, base_path=tmp_path)
