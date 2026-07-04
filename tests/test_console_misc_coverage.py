"""Coverage — console commands: lang:list, route:list, make:* error path (doc 13)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from arvel.console import build_cli

runner = CliRunner()


def test_lang_list_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lang = tmp_path / "lang"
    lang.mkdir()
    (lang / "en.json").write_text("{}")
    (lang / "es.json").write_text("{}")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(build_cli(), ["lang:list"])
    assert result.exit_code == 0
    assert "en" in result.output
    assert "es" in result.output


def test_lang_list_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(build_cli(), ["lang:list"])
    assert result.exit_code == 0
    assert "no locales" in result.output.lower()


def test_make_model_already_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(build_cli(), ["make:model", "Widget"]).exit_code == 0
    second = runner.invoke(build_cli(), ["make:model", "Widget"])
    assert second.exit_code == 1
    assert "already exists" in second.output


def test_route_list_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # route:list boots the project app via the console kernel, so it needs a bootstrap/app.py
    (tmp_path / "bootstrap").mkdir()
    (tmp_path / "bootstrap" / "app.py").write_text(
        "from arvel.kernel import Application\n\n"
        "def create_app():\n"
        "    app = Application(base_path='.')\n"
        "    app.route_files.append('routes/web.py')\n"
        "    return app\n"
    )
    (tmp_path / "routes").mkdir()
    (tmp_path / "routes" / "web.py").write_text(
        "from arvel import Route\n\nRoute.get('/ping', lambda request: {}, name='ping')\n"
    )
    monkeypatch.chdir(tmp_path)
    from arvel.kernel import set_application

    try:
        result = runner.invoke(build_cli(), ["route:list"])
        assert result.exit_code == 0, result.output
        assert "/ping" in result.output
    finally:
        set_application(None)


def test_route_list_without_app() -> None:
    from arvel.kernel import set_application

    set_application(None)
    result = runner.invoke(build_cli(), ["route:list"])
    assert result.exit_code == 1  # no app/router bound
