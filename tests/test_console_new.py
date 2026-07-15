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
    # the scaffold must carry every engine its OWN generated code defaults to. `standard`
    # includes sqlite (config/database.py's default DB) and view (the home route renders a
    # template) precisely so this one extra keeps a fresh `arvel new` + `uv sync` app able
    # to migrate AND serve its home page. Pin the full dependency line so a commented-out
    # or partial dep can't satisfy this test.
    scaffold_pyproject = (tmp_path / "myapp" / "pyproject.toml").read_text()
    assert 'dependencies = ["arvel[standard]"]' in scaffold_pyproject


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


def test_new_package_scaffolds_full_skeleton(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--package renders the maximal-subtractive skeleton: every contribution type
    present as a small working example, the rest discoverable as commented verbs."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(build_cli(), ["new", "my-pkg", "--package"])
    assert result.exit_code == 0, result.output
    root = tmp_path / "my-pkg"
    for rel in (
        "pyproject.toml",
        "README.md",
        "src/arvel_my_pkg/__init__.py",
        "src/arvel_my_pkg/py.typed",
        "src/arvel_my_pkg/provider.py",
        "src/arvel_my_pkg/settings.py",
        "src/arvel_my_pkg/contracts.py",
        "src/arvel_my_pkg/manager.py",
        "src/arvel_my_pkg/drivers.py",
        "src/arvel_my_pkg/facade.py",
        "src/arvel_my_pkg/routes.py",
        "src/arvel_my_pkg/commands.py",
        "tests/conftest.py",
        "tests/test_provider.py",
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
        "Makefile",
        ".pre-commit-config.yaml",
    ):
        assert (root / rel).exists(), rel
    pyproject = (root / "pyproject.toml").read_text()
    assert 'name = "arvel-my-pkg"' in pyproject
    assert '"arvel.providers"' in pyproject
    assert "[tool.importlinter]" in pyproject
    # provider documents every integration verb (commented = inert but discoverable)
    provider = (root / "src" / "arvel_my_pkg" / "provider.py").read_text()
    for verb in (
        "merge_config_from",
        "load_routes_from",
        "load_migrations_from",
        "load_views_from",
        "load_translations_from",
        "publishes",
        "commands",
    ):
        assert verb in provider, verb
    # README carries the keep/delete pruning guide
    readme = (root / "README.md").read_text()
    assert "delete" in readme.lower()


def test_new_package_generated_tests_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The un-pruned skeleton is green out of the box: its own test suite passes
    against the current arvel checkout (anti-rot gate for the template)."""
    import os
    import subprocess
    import sys

    monkeypatch.chdir(tmp_path)
    assert runner.invoke(build_cli(), ["new", "demo", "--package"]).exit_code == 0
    root = tmp_path / "demo"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


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
