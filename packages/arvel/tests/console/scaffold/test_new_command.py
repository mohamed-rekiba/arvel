"""``arvel new <name>`` CLI surface.

Uses Typer's ``CliRunner`` against the same Typer app the framework binary
builds (``build_app``). Covers input validation (invalid names → exit 2),
the happy path (generates a project from the packaged skeleton), pre-existing
target handling, and the `--no-install` / `--python` flags.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from arvel.console.entrypoint import build_app
from click.testing import CliRunner as ClickCliRunner
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    """Typer CliRunner — Click 8.2+ keeps stderr separate by default."""
    return CliRunner()


def test_help_lists_new_subcommand(runner: CliRunner) -> None:
    """`arvel --help` shows the `new` subcommand."""
    app = build_app()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "new" in result.stdout


def test_new_help_shows_name_argument_and_flags(runner: CliRunner) -> None:
    app = build_app()
    result = runner.invoke(app, ["new", "--help"])
    assert result.exit_code == 0
    assert "NAME" in result.stdout
    assert "--no-install" in result.stdout
    assert "--python" in result.stdout


@pytest.mark.parametrize(
    "bad_name",
    ["My-App", "1numeric", "../escape", "my.app", "my app", "my/app", ""],
)
def test_new_rejects_invalid_names_with_exit_2(
    runner: CliRunner, bad_name: str, tmp_path: Path
) -> None:
    """Invalid names → exit 2 with stderr mention of the violation."""
    app = build_app()
    with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app, ["new", bad_name])
        # Empty name is rejected by Typer itself as a missing arg → exit 2.
        # Other invalid names are rejected by validate_project_name → exit 2.
        assert result.exit_code == 2


def test_new_happy_path_creates_target_directory(runner: CliRunner, tmp_path: Path) -> None:
    """Valid name + clean cwd → exit 0, target populated."""
    app = build_app()
    with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path) as iso_cwd:
        result = runner.invoke(app, ["new", "my-app", "--no-install"])
        assert result.exit_code == 0, result.stderr
        assert (Path(iso_cwd) / "my-app").is_dir()


def test_new_no_install_skips_uv_sync(runner: CliRunner, tmp_path: Path) -> None:
    """``--no-install`` means no .venv/ in the generated target."""
    app = build_app()
    with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path) as iso_cwd:
        result = runner.invoke(app, ["new", "my-app", "--no-install"])
        assert result.exit_code == 0, result.stderr
        target = Path(iso_cwd) / "my-app"
        assert target.is_dir()
        assert not (target / ".venv").exists()
        assert not (target / "uv.lock").exists()


def test_new_python_flag_pins_requires_python(runner: CliRunner, tmp_path: Path) -> None:
    """``--python`` writes through to the generated ``pyproject.toml``."""
    app = build_app()
    with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path) as iso_cwd:
        result = runner.invoke(app, ["new", "my-app", "--no-install", "--python", "3.14"])
        assert result.exit_code == 0, result.stderr
        pyproject = (Path(iso_cwd) / "my-app" / "pyproject.toml").read_text()
        assert 'requires-python = ">=3.14"' in pyproject


def test_new_next_steps_output_includes_run_commands(runner: CliRunner, tmp_path: Path) -> None:
    """stdout includes the cd + uv run arvel serve instructions."""
    app = build_app()
    with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app, ["new", "my-app", "--no-install"])
        assert result.exit_code == 0, result.stderr
        assert "cd my-app" in result.stdout
        assert "uv run arvel serve" in result.stdout


def test_new_refuses_to_overwrite_non_empty_dir(runner: CliRunner, tmp_path: Path) -> None:
    """Pre-existing non-empty target → exit 1."""
    app = build_app()
    with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path) as iso_cwd:
        target = Path(iso_cwd) / "my-app"
        target.mkdir()
        (target / "do-not-clobber.txt").write_text("important")

        result = runner.invoke(app, ["new", "my-app", "--no-install"])
        assert result.exit_code == 1
        # Content preserved.
        assert (target / "do-not-clobber.txt").read_text() == "important"


def test_new_accepts_pre_existing_empty_dir(runner: CliRunner, tmp_path: Path) -> None:
    """Pre-existing empty target → exit 0, used into."""
    app = build_app()
    with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path) as iso_cwd:
        (Path(iso_cwd) / "my-app").mkdir()

        result = runner.invoke(app, ["new", "my-app", "--no-install"])
        assert result.exit_code == 0, result.stderr
        assert (Path(iso_cwd) / "my-app" / "bootstrap" / "app.py").exists()
