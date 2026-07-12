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
    # `standard` is deliberately slim (http/server/console); the scaffold adds `sqlite`
    # explicitly because its generated config defaults to sqlite — without the driver a
    # fresh `arvel new` + `uv sync` app cannot open its own database
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


# -- A8: package name derives from the path's basename, not the whole path -------------------


def test_derive_package_name_basename_matrix() -> None:
    from arvel.console.builtins import _derive_package_name

    assert _derive_package_name("myapp") == "myapp"
    assert _derive_package_name("/abs/path/my-app") == "my-app"
    assert _derive_package_name("/abs/path/my-app/") == "my-app"  # trailing slash
    assert _derive_package_name("./relative/My_App") == "my-app"
    assert _derive_package_name("Weird--Name!!") == "weird-name"
    assert _derive_package_name("/") == ""  # invalid: no basename to derive from
    assert _derive_package_name("---") == ""  # invalid: sanitizes to empty


def test_new_absolute_path_names_the_package_from_the_basename(tmp_path: Path) -> None:
    """The live-repro'd A8 bug: scaffolding to an absolute path must NOT leak the whole path into
    the package name / pyproject / welcome title."""
    target = tmp_path / "my-app"
    result = runner.invoke(build_cli(), ["new", str(target)])
    assert result.exit_code == 0, result.output
    pyproject = (target / "pyproject.toml").read_text()
    assert 'name = "my-app"' in pyproject
    web = (target / "routes" / "web.py").read_text()
    assert '"title": "my-app"' in web
    assert str(target) not in pyproject  # the whole path must never leak into the package name


def test_new_absolute_path_with_trailing_slash(tmp_path: Path) -> None:
    target = tmp_path / "trailing-app"
    result = runner.invoke(build_cli(), ["new", str(target) + "/"])
    assert result.exit_code == 0, result.output
    assert 'name = "trailing-app"' in (target / "pyproject.toml").read_text()


def test_new_invalid_basename_errors_clearly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(build_cli(), ["new", "___"])  # sanitizes to "" — no valid basename
    assert result.exit_code == 1
    assert "valid package name" in result.output


def test_new_package_absolute_path_names_from_basename(tmp_path: Path) -> None:
    target = tmp_path / "my-pkg"
    result = runner.invoke(build_cli(), ["new", str(target), "--package"])
    assert result.exit_code == 0, result.output
    pyproject = (target / "pyproject.toml").read_text()
    assert 'name = "arvel-my-pkg"' in pyproject
    assert (target / "src" / "arvel_my_pkg" / "provider.py").exists()


def test_new_app_is_born_with_a_crypto_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(build_cli(), ["new", "keyed"]).exit_code == 0
    env_file = tmp_path / "keyed" / ".env"
    assert env_file.is_file()  # .env.example mirrored into a live .env
    key_line = next(
        line for line in env_file.read_text().splitlines() if line.startswith("APP_KEY=")
    )
    assert len(key_line.removeprefix("APP_KEY=")) >= 40  # a real generated key, not a stub
