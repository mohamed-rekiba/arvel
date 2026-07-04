"""Scaffold acceptance: `arvel new` produces a RUNNABLE project.

The consumer-path proof at the pytest layer: a freshly-scaffolded app has the `create_app()` factory
(the in_project marker + what the CLI/asgi load), is recognized as a project, and serves its `/` route
through the booted console kernel. The full HTTP serve is also covered by tools/e2e_smoke.sh.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from arvel.console import build_cli

runner = CliRunner()


def test_new_scaffolds_a_runnable_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(build_cli(), ["new", "blog"]).exit_code == 0

    proj = tmp_path / "blog"
    app_py = (proj / "bootstrap" / "app.py").read_text()
    assert (
        "def create_app()" in app_py
    )  # the factory the CLI + asgi load (also the in_project marker)
    assert "with_routing(" in app_py and "web.py" in app_py  # routes wired so they're served
    assert (
        "create_app()" in (proj / "asgi.py").read_text()
    )  # asgi uses the factory, not bare Application()

    from arvel.console.context import in_project
    from arvel.kernel import set_application

    monkeypatch.chdir(proj)
    assert in_project() is True  # fresh project is recognized
    try:
        result = runner.invoke(build_cli(), ["route:list"])  # boots the app via the console kernel
        assert result.exit_code == 0, result.output
        assert (
            "/" in result.output and "home" in result.output
        )  # the scaffolded route is registered
    finally:
        set_application(None)


def test_new_scaffolds_a_laravel_like_structure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # a fresh app ships a minimal-but-real structure (cf. `laravel new`)
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(build_cli(), ["new", "blog"]).exit_code == 0
    proj = tmp_path / "blog"
    for rel in (
        ".env.example",
        ".gitignore",
        "config/app.py",
        "app/models/user.py",
        "app/providers/app_provider.py",
        "bootstrap/providers.py",
        "bootstrap/middlewares.py",
        "config/database.py",
        "config/auth.py",
        "config/openapi.py",
        "database/seeders/database_seeder.py",
        "database/factories/user_factory.py",
        "database/migrations/0001_01_01_000000_create_users_table.py",
        "database/migrations/0001_01_01_000001_create_personal_access_tokens_table.py",
        "routes/web.py",
        "routes/api.py",
        "routes/console.py",
        "resources/views/welcome.html",
        "tests/test_example.py",
        "tests/test_database.py",
    ):
        assert (proj / rel).is_file(), f"scaffold missing {rel}"
    assert "class AppServiceProvider" in (proj / "app/providers/app_provider.py").read_text()
    assert "class User" in (proj / "app/models/user.py").read_text()
    # providers + middlewares wired via the fluent builder (Laravel-style bootstrap files)
    app_py = (proj / "bootstrap/app.py").read_text()
    assert "with_providers(" in app_py and "with_middlewares(" in app_py
    assert "providers = [AppServiceProvider]" in (proj / "bootstrap/providers.py").read_text()
