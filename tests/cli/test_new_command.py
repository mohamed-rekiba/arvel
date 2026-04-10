"""Tests for the `arvel new` CLI command (integration-level)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from arvel.cli.app import app

runner = CliRunner()

MOCK_REGISTRY = [
    {
        "name": "default",
        "description": "Official Arvel starter",
        "repo": "https://github.com/mohamed-rekiba/arvel-starter",
        "default": True,
    }
]


@pytest.fixture
def mock_skeleton(tmp_path: Path) -> Path:
    """Create a minimal skeleton to avoid GitHub downloads."""
    skel = tmp_path / "skel"
    skel.mkdir()
    (skel / "main.py.j2").write_text('APP = "{{ app_name }}"\n')
    (skel / ".env.example.j2").write_text(
        "APP_KEY={{ secret_key }}\nDB_DRIVER={{ database_driver }}\n"
        "DB_URL={{ database_url }}\nCACHE_DRIVER={{ cache_driver }}\n"
        "QUEUE_DRIVER={{ queue_driver }}\nMAIL_DRIVER={{ mail_driver }}\n"
        "STORAGE_DRIVER={{ storage_driver }}\nSEARCH_DRIVER={{ search_driver }}\n"
        "BROADCAST_DRIVER={{ broadcast_driver }}\n"
    )
    (skel / "pyproject.toml.j2").write_text(
        '[project]\nname = "{{ app_name }}"\n'
        'dependencies = ["arvel{{ arvel_extras }}>={{ arvel_version }}"]\n'
    )
    (skel / ".gitignore").write_text(".venv/\n.env\n")
    cfg = skel / "config"
    cfg.mkdir()
    (cfg / "database.py.j2").write_text('SA_DRIVER = "{{ database_sa_driver }}"\n')
    app_dir = skel / "app" / "modules"
    app_dir.mkdir(parents=True)
    (app_dir / ".gitkeep").write_text("")
    return skel


def _patch_network(mock_skeleton: Path):
    """Patch both registry fetch and skeleton download."""
    return (
        patch(
            "arvel.cli.commands.new._fetch_templates_registry",
            return_value=MOCK_REGISTRY,
        ),
        patch(
            "arvel.cli.commands.new._download_skeleton",
            return_value=mock_skeleton,
        ),
    )


class TestNewCommandValidation:
    def test_missing_name_shows_help(self) -> None:
        result = runner.invoke(app, ["new"])
        assert result.exit_code != 0

    def test_invalid_name(self) -> None:
        result = runner.invoke(
            app,
            ["new", "1invalid", "--no-input", "--no-install", "--no-git"],
            catch_exceptions=False,
        )
        assert result.exit_code != 0
        assert "Invalid project name" in result.output

    def test_existing_dir_without_force_fails(self, tmp_path: Path) -> None:
        target = tmp_path / "existapp"
        target.mkdir()
        old_cwd = Path.cwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(
                app,
                ["new", "existapp", "--no-input", "--no-install", "--no-git"],
                catch_exceptions=False,
            )
            assert result.exit_code != 0
            assert "already exists" in result.output
        finally:
            os.chdir(old_cwd)


class TestNewCommandScaffold:
    def test_creates_project(self, tmp_path: Path, mock_skeleton: Path) -> None:
        old_cwd = Path.cwd()
        os.chdir(tmp_path)
        try:
            p_reg, p_dl = _patch_network(mock_skeleton)
            with p_reg, p_dl:
                result = runner.invoke(
                    app,
                    ["new", "testapp", "--no-input", "--no-install", "--no-git"],
                    catch_exceptions=False,
                )
            assert result.exit_code == 0
            assert (tmp_path / "testapp" / "main.py").exists()
        finally:
            os.chdir(old_cwd)

    def test_force_overwrites(self, tmp_path: Path, mock_skeleton: Path) -> None:
        target = tmp_path / "forceapp"
        target.mkdir()
        (target / "old.txt").write_text("old")
        old_cwd = Path.cwd()
        os.chdir(tmp_path)
        try:
            p_reg, p_dl = _patch_network(mock_skeleton)
            with p_reg, p_dl:
                result = runner.invoke(
                    app,
                    [
                        "new",
                        "forceapp",
                        "--force",
                        "--no-input",
                        "--no-install",
                        "--no-git",
                    ],
                    catch_exceptions=False,
                )
            assert result.exit_code == 0
            assert not (target / "old.txt").exists()
        finally:
            os.chdir(old_cwd)

    def test_database_postgres(self, tmp_path: Path, mock_skeleton: Path) -> None:
        old_cwd = Path.cwd()
        os.chdir(tmp_path)
        try:
            p_reg, p_dl = _patch_network(mock_skeleton)
            with p_reg, p_dl:
                result = runner.invoke(
                    app,
                    [
                        "new",
                        "pgapp",
                        "--database",
                        "postgres",
                        "--no-input",
                        "--no-install",
                        "--no-git",
                    ],
                    catch_exceptions=False,
                )
            assert result.exit_code == 0
            db_cfg = (tmp_path / "pgapp" / "config" / "database.py").read_text()
            assert "postgresql+asyncpg" in db_cfg
            env_content = (tmp_path / "pgapp" / ".env").read_text()
            assert "DB_DRIVER=pgsql" in env_content
        finally:
            os.chdir(old_cwd)

    def test_secret_key_generated(self, tmp_path: Path, mock_skeleton: Path) -> None:
        old_cwd = Path.cwd()
        os.chdir(tmp_path)
        try:
            p_reg, p_dl = _patch_network(mock_skeleton)
            with p_reg, p_dl:
                result = runner.invoke(
                    app,
                    ["new", "keyapp", "--no-input", "--no-install", "--no-git"],
                    catch_exceptions=False,
                )
            assert result.exit_code == 0
            env_content = (tmp_path / "keyapp" / ".env").read_text()
            assert "APP_KEY=" in env_content
            key = env_content.split("APP_KEY=")[1].split("\n")[0]
            assert len(key) == 64
        finally:
            os.chdir(old_cwd)

    def test_summary_printed(self, tmp_path: Path, mock_skeleton: Path) -> None:
        old_cwd = Path.cwd()
        os.chdir(tmp_path)
        try:
            p_reg, p_dl = _patch_network(mock_skeleton)
            with p_reg, p_dl:
                result = runner.invoke(
                    app,
                    ["new", "demoapp", "--no-input", "--no-install", "--no-git"],
                    catch_exceptions=False,
                )
            assert "Build something amazing" in result.output
            assert "cd demoapp" in result.output
        finally:
            os.chdir(old_cwd)


class TestTemplatesRegistry:
    def test_resolve_default_template(self) -> None:
        from arvel.cli.commands.new import _resolve_template_repo

        repo = _resolve_template_repo(MOCK_REGISTRY)
        assert repo == "https://github.com/mohamed-rekiba/arvel-starter"

    def test_resolve_named_template(self) -> None:
        from arvel.cli.commands.new import _resolve_template_repo

        repo = _resolve_template_repo(MOCK_REGISTRY, "default")
        assert repo == "https://github.com/mohamed-rekiba/arvel-starter"

    def test_resolve_unknown_template_fails(self) -> None:
        from arvel.cli.commands.new import _resolve_template_repo

        with pytest.raises(SystemExit, match="Unknown template"):
            _resolve_template_repo(MOCK_REGISTRY, "nonexistent")

    def test_bundled_fallback(self) -> None:
        from arvel.cli.commands.new import _load_bundled_registry

        templates = _load_bundled_registry()
        assert len(templates) >= 1
        assert templates[0]["name"] == "default"

    def test_repo_to_owner_name(self) -> None:
        from arvel.cli.commands.new import _repo_to_owner_name

        assert (
            _repo_to_owner_name("https://github.com/mohamed-rekiba/arvel-starter")
            == "mohamed-rekiba/arvel-starter"
        )
        assert _repo_to_owner_name("owner/repo") == "owner/repo"
