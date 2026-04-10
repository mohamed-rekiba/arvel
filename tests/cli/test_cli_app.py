"""Tests for FR-35 through FR-38: CLI Bootstrap.

Covers the Typer CLI app, command groups, and entry point.
"""

from __future__ import annotations


class TestCliAppImport:
    """FR-35: CLI app importable."""

    def test_cli_app_importable(self) -> None:
        from arvel.cli.app import app

        assert app is not None

    def test_cli_app_is_typer_instance(self) -> None:
        import typer

        from arvel.cli.app import app

        assert isinstance(app, typer.Typer)


class TestCliDbCommands:
    """FR-36: db command group exists."""

    def test_db_group_registered(self) -> None:
        from typer.testing import CliRunner

        from arvel.cli.app import app

        runner = CliRunner()
        result = runner.invoke(app, ["db", "--help"])
        assert result.exit_code == 0
        assert "migrate" in result.output or "seed" in result.output

    def test_migrate_help(self) -> None:
        from typer.testing import CliRunner

        from arvel.cli.app import app

        runner = CliRunner()
        result = runner.invoke(app, ["db", "migrate", "--help"])
        assert result.exit_code == 0

    def test_seed_help(self) -> None:
        from typer.testing import CliRunner

        from arvel.cli.app import app

        runner = CliRunner()
        result = runner.invoke(app, ["db", "seed", "--help"])
        assert result.exit_code == 0

    def test_migrate_status_help(self) -> None:
        from typer.testing import CliRunner

        from arvel.cli.app import app

        runner = CliRunner()
        result = runner.invoke(app, ["db", "status", "--help"])
        assert result.exit_code == 0

    def test_migrate_rollback_help(self) -> None:
        from typer.testing import CliRunner

        from arvel.cli.app import app

        runner = CliRunner()
        result = runner.invoke(app, ["db", "rollback", "--help"])
        assert result.exit_code == 0

    def test_migrate_fresh_help(self) -> None:
        from typer.testing import CliRunner

        from arvel.cli.app import app

        runner = CliRunner()
        result = runner.invoke(app, ["db", "fresh", "--help"])
        assert result.exit_code == 0


class TestCliMakeCommands:
    """FR-36: make command group for generators."""

    def test_make_group_registered(self) -> None:
        from typer.testing import CliRunner

        from arvel.cli.app import app

        runner = CliRunner()
        result = runner.invoke(app, ["make", "--help"])
        assert result.exit_code == 0

    def test_make_migration_help(self) -> None:
        from typer.testing import CliRunner

        from arvel.cli.app import app

        runner = CliRunner()
        result = runner.invoke(app, ["make", "migration", "--help"])
        assert result.exit_code == 0

    def test_make_seeder_help(self) -> None:
        from typer.testing import CliRunner

        from arvel.cli.app import app

        runner = CliRunner()
        result = runner.invoke(app, ["make", "seeder", "--help"])
        assert result.exit_code == 0


class TestCliViewCommands:
    """FR-36: view command group exists."""

    def test_view_group_registered(self) -> None:
        from typer.testing import CliRunner

        from arvel.cli.app import app

        runner = CliRunner()
        result = runner.invoke(app, ["view", "--help"])
        assert result.exit_code == 0

    def test_view_refresh_help(self) -> None:
        from typer.testing import CliRunner

        from arvel.cli.app import app

        runner = CliRunner()
        result = runner.invoke(app, ["view", "refresh", "--help"])
        assert result.exit_code == 0


class TestCliBanner:
    """CLI prints a banner when invoked without subcommand."""

    def test_banner_displayed(self) -> None:
        from typer.testing import CliRunner

        from arvel.cli.app import app

        runner = CliRunner()
        result = runner.invoke(app, [])
        assert "Arvel" in result.output or "Framework" in result.output

    def test_version_flag(self) -> None:
        from typer.testing import CliRunner

        from arvel.cli.app import app

        runner = CliRunner()
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "arvel" in result.output.lower()


class TestCliExitCodes:
    """NFR-07: CLI exits with 0 on success, non-zero on failure."""

    def test_help_exits_zero(self) -> None:
        from typer.testing import CliRunner

        from arvel.cli.app import app

        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
