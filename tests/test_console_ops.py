"""Console ops commands (Laravel parity) — key:generate, storage:link, cache:clear."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from arvel.console import build_cli

runner = CliRunner()


def test_key_generate_writes_app_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(build_cli(), ["key:generate"])
    assert result.exit_code == 0, result.output
    body = (tmp_path / ".env").read_text()
    assert body.startswith("APP_KEY=") and len(body.strip()) > len("APP_KEY=")


def test_storage_link_creates_symlink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(build_cli(), ["storage:link"])
    assert result.exit_code == 0, result.output
    link = tmp_path / "public/storage"
    assert link.is_symlink()
    # second run refuses (already exists)
    assert runner.invoke(build_cli(), ["storage:link"]).exit_code == 1


def test_cache_clear_flushes_the_store() -> None:
    from arvel.cache import CacheManager
    from arvel.kernel import Application, set_application

    app = Application()
    app.instance("cache", CacheManager(app).create_array_driver())
    set_application(app)
    try:
        result = runner.invoke(build_cli(), ["cache:clear"])
        assert result.exit_code == 0, result.output
        assert "cache cleared" in result.output
    finally:
        set_application(None)
