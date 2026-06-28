"""Console (doc 13) — `arvel new` scaffolds a real project / package tree."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from arvel.console import build_cli

runner = CliRunner()


def test_new_scaffolds_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(build_cli(), ["new", "myapp"])
    assert result.exit_code == 0, result.output
    for rel in ("pyproject.toml", "asgi.py", "app/__init__.py", "routes/web.py"):
        assert (tmp_path / "myapp" / rel).exists(), rel
    assert "arvel[standard,sqlite]" in (tmp_path / "myapp" / "pyproject.toml").read_text()


def test_new_web_profile_adds_views(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(build_cli(), ["new", "site", "--profile", "web"])
    assert (tmp_path / "site" / "resources" / "views" / "welcome.html").exists()


def test_new_auth_adds_the_bearer_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(build_cli(), ["new", "secured", "--auth"]).exit_code == 0
    api = (tmp_path / "secured" / "routes" / "api.py").read_text()
    assert "def login" in api and "create_token" in api and "TokenGuard" in api
    assert (tmp_path / "secured" / "tests" / "test_auth.py").is_file()


def test_new_package_declares_entry_point(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(build_cli(), ["new", "stripe", "--package"])
    assert result.exit_code == 0
    pyproject = (tmp_path / "stripe" / "pyproject.toml").read_text()
    assert "arvel.providers" in pyproject
    assert (tmp_path / "stripe" / "src" / "arvel_stripe" / "provider.py").exists()


def test_new_existing_path_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "taken").mkdir()
    assert runner.invoke(build_cli(), ["new", "taken"]).exit_code == 1
