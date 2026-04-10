"""Tests for FR-020-04: Config Cache (arvel config cache / clear).

All tests are written BEFORE implementation (QA-Pre / Stage 3a).
They must compile but FAIL until the implementation is complete.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from arvel.cli.app import app

if TYPE_CHECKING:
    import pytest

runner = CliRunner()


class TestConfigCommandsRegistered:
    """Config command group is accessible."""

    def test_config_help(self) -> None:
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0
        assert "cache" in result.output.lower()

    def test_config_cache_help(self) -> None:
        result = runner.invoke(app, ["config", "cache", "--help"])
        assert result.exit_code == 0

    def test_config_clear_help(self) -> None:
        result = runner.invoke(app, ["config", "clear", "--help"])
        assert result.exit_code == 0

    def test_config_export_help(self) -> None:
        result = runner.invoke(app, ["config", "export", "--help"])
        assert result.exit_code == 0


class TestConfigCache:
    """FR-020-04.1: arvel config cache serializes config to JSON."""

    def test_config_cache_creates_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        (tmp_path / "bootstrap" / "cache").mkdir(parents=True, exist_ok=True)

        result = runner.invoke(app, ["config", "cache"])
        assert result.exit_code == 0

        cache_file = tmp_path / "bootstrap" / "cache" / "config.json"
        assert cache_file.exists()

    def test_config_cache_is_valid_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        (tmp_path / "bootstrap" / "cache").mkdir(parents=True, exist_ok=True)

        runner.invoke(app, ["config", "cache"])

        cache_file = tmp_path / "bootstrap" / "cache" / "config.json"
        data = json.loads(cache_file.read_text())
        assert isinstance(data, dict)
        assert "app_name" in data


class TestConfigCachePermissions:
    """FR-020-04.4: Cache file has restricted permissions (0600)."""

    def test_config_cache_has_restricted_permissions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        (tmp_path / "bootstrap" / "cache").mkdir(parents=True, exist_ok=True)

        runner.invoke(app, ["config", "cache"])

        cache_file = tmp_path / "bootstrap" / "cache" / "config.json"
        permissions = stat.S_IMODE(cache_file.stat().st_mode)
        assert permissions == 0o600


class TestConfigCacheExcludesSecrets:
    """FR-020-04.5: SecretStr fields excluded from cache."""

    def test_config_cache_excludes_app_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        monkeypatch.setenv("APP_KEY", "super-secret-key")
        (tmp_path / "bootstrap" / "cache").mkdir(parents=True, exist_ok=True)

        runner.invoke(app, ["config", "cache"])

        cache_file = tmp_path / "bootstrap" / "cache" / "config.json"
        data = json.loads(cache_file.read_text())
        assert "app_key" not in data
        assert "super-secret-key" not in cache_file.read_text()


class TestConfigClear:
    """FR-020-04.3: arvel config clear deletes the cache file."""

    def test_config_clear_removes_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        cache_dir = tmp_path / "bootstrap" / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "config.json").write_text("{}")

        result = runner.invoke(app, ["config", "clear"])
        assert result.exit_code == 0
        assert not (cache_dir / "config.json").exists()

    def test_config_clear_when_no_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        (tmp_path / "bootstrap" / "cache").mkdir(parents=True, exist_ok=True)

        result = runner.invoke(app, ["config", "clear"])
        assert result.exit_code == 0


class TestConfigCacheCorruption:
    """FR-020-04.6: Corrupted cache falls back gracefully."""

    def test_corrupted_cache_triggers_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        cache_dir = tmp_path / "bootstrap" / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "config.json").write_text("NOT VALID JSON {{{")

        import asyncio

        from arvel.foundation.config import load_config

        config = asyncio.run(load_config(tmp_path, cache_path=cache_dir / "config.json"))
        assert config.app_name == "Arvel"


class TestConfigExport:
    """Export framework default config files and skip existing files."""

    def test_export_creates_missing_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

        result = runner.invoke(app, ["config", "export"])
        assert result.exit_code == 0
        database_config = tmp_path / "config" / "database.py"
        assert database_config.exists()
        assert (tmp_path / "config" / "observability.py").exists()
        assert (tmp_path / "config" / "app.py").exists()
        assert (tmp_path / "config" / "auth.py").exists()
        assert (tmp_path / "config" / "session.py").exists()
        content = database_config.read_text()
        assert "class DatabaseSettings(ModuleSettings):" in content
        assert "SettingsConfigDict" in content
        assert "\nconfig = {" not in content

    def test_export_skips_existing_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        existing = config_dir / "database.py"
        existing.write_text("config = {'database': 'existing'}\n")

        result = runner.invoke(app, ["config", "export"])
        assert result.exit_code == 0
        assert "Skipped existing" in result.output
        assert existing.read_text() == "config = {'database': 'existing'}\n"

    def test_export_dry_run_does_not_write(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

        result = runner.invoke(app, ["config", "export", "--dry-run"])
        assert result.exit_code == 0
        assert "Would create:" in result.output
        assert not (tmp_path / "config" / "database.py").exists()
        assert not (tmp_path / "config" / "app.py").exists()
