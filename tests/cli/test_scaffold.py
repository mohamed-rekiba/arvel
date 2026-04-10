"""Tests for project scaffolding — template rendering and file structure."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from arvel.cli.commands.new import (
    DATABASE_CONFIGS,
    render_skeleton,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def skeleton_dir(tmp_path: Path) -> Path:
    """Create a minimal skeleton with .j2 templates."""
    skel = tmp_path / "skeleton"
    skel.mkdir()

    (skel / "main.py.j2").write_text(
        '"""{{ app_name }} entry point."""\nAPP_NAME = "{{ app_name }}"\n'
    )
    (skel / "pyproject.toml.j2").write_text(
        '[project]\nname = "{{ app_name }}"\ndependencies = ["arvel=={{ arvel_version }}"]\n'
    )
    (skel / ".env.example.j2").write_text(
        "APP_KEY={{ secret_key }}\nDATABASE_URL={{ database_url }}\n"
    )

    config_dir = skel / "config"
    config_dir.mkdir()
    (config_dir / "database.py.j2").write_text('DATABASE_DRIVER = "{{ database_driver }}"\n')

    (skel / ".gitignore").write_text(".venv/\n.env\n__pycache__/\n")

    app_dir = skel / "app" / "modules"
    app_dir.mkdir(parents=True)
    (app_dir / ".gitkeep").write_text("")

    return skel


class TestRenderSkeleton:
    def test_renders_j2_files(self, skeleton_dir: Path, tmp_path: Path) -> None:
        target = tmp_path / "myapp"
        render_skeleton(
            skeleton_dir=skeleton_dir,
            target_dir=target,
            context={
                "app_name": "myapp",
                "app_name_title": "Myapp",
                "database_driver": "sqlite+aiosqlite",
                "database_url": "sqlite+aiosqlite:///database/database.sqlite",
                "python_version": "3.14",
                "arvel_version": "0.1.0",
                "secret_key": "abc123",
            },
        )

        main_py = target / "main.py"
        assert main_py.exists()
        content = main_py.read_text()
        assert 'APP_NAME = "myapp"' in content

    def test_j2_files_removed(self, skeleton_dir: Path, tmp_path: Path) -> None:
        target = tmp_path / "myapp"
        render_skeleton(
            skeleton_dir=skeleton_dir,
            target_dir=target,
            context={
                "app_name": "myapp",
                "app_name_title": "Myapp",
                "database_driver": "sqlite+aiosqlite",
                "database_url": "sqlite+aiosqlite:///database/database.sqlite",
                "python_version": "3.14",
                "arvel_version": "0.1.0",
                "secret_key": "abc123",
            },
        )
        j2_files = list(target.rglob("*.j2"))
        assert len(j2_files) == 0

    def test_non_j2_files_copied(self, skeleton_dir: Path, tmp_path: Path) -> None:
        target = tmp_path / "myapp"
        render_skeleton(
            skeleton_dir=skeleton_dir,
            target_dir=target,
            context={
                "app_name": "myapp",
                "app_name_title": "Myapp",
                "database_driver": "sqlite+aiosqlite",
                "database_url": "sqlite+aiosqlite:///database/database.sqlite",
                "python_version": "3.14",
                "arvel_version": "0.1.0",
                "secret_key": "abc123",
            },
        )
        assert (target / ".gitignore").exists()
        assert (target / "app" / "modules" / ".gitkeep").exists()

    def test_env_file_created(self, skeleton_dir: Path, tmp_path: Path) -> None:
        target = tmp_path / "myapp"
        render_skeleton(
            skeleton_dir=skeleton_dir,
            target_dir=target,
            context={
                "app_name": "myapp",
                "app_name_title": "Myapp",
                "database_driver": "sqlite+aiosqlite",
                "database_url": "sqlite+aiosqlite:///database/database.sqlite",
                "python_version": "3.14",
                "arvel_version": "0.1.0",
                "secret_key": "abc123",
            },
        )
        env_example = target / ".env.example"
        assert env_example.exists()
        content = env_example.read_text()
        assert "APP_KEY=abc123" in content

    def test_database_config_rendered(self, skeleton_dir: Path, tmp_path: Path) -> None:
        target = tmp_path / "myapp"
        render_skeleton(
            skeleton_dir=skeleton_dir,
            target_dir=target,
            context={
                "app_name": "myapp",
                "app_name_title": "Myapp",
                "database_driver": "postgresql+asyncpg",
                "database_url": "postgresql+asyncpg://localhost:5432/myapp",
                "python_version": "3.14",
                "arvel_version": "0.1.0",
                "secret_key": "abc123",
            },
        )
        db_config = target / "config" / "database.py"
        assert db_config.exists()
        assert "postgresql+asyncpg" in db_config.read_text()


class TestDatabaseConfigs:
    def test_sqlite_config(self) -> None:
        cfg = DATABASE_CONFIGS["sqlite"]
        assert cfg["driver"] == "sqlite+aiosqlite"

    def test_postgres_config(self) -> None:
        cfg = DATABASE_CONFIGS["postgres"]
        assert cfg["driver"] == "postgresql+asyncpg"

    def test_mysql_config(self) -> None:
        cfg = DATABASE_CONFIGS["mysql"]
        assert cfg["driver"] == "mysql+aiomysql"

    def test_url_contains_app_name(self) -> None:
        cfg = DATABASE_CONFIGS["postgres"]
        url = cfg["url_template"].format(app_name="myapp")
        assert "myapp" in url
