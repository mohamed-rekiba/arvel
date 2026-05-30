"""model:show command."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest
import typer
from arvel.console.commands.model_show import ModelShowCommand
from typer.testing import CliRunner


class _UserModel:
    table = "users"
    visible = ["id", "email"]
    hidden = ["password"]
    __annotations__ = {"id": int, "email": str}


def test_model_show_rejects_non_dotted_paths() -> None:
    app = typer.Typer()
    ModelShowCommand().register(app)

    result = CliRunner().invoke(app, ["User"])

    assert result.exit_code == 2
    assert "not a dotted path" in result.stderr


def test_model_show_prints_model_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    def import_module(name: str) -> object:
        assert name == "app.models"
        return SimpleNamespace(User=_UserModel)

    monkeypatch.setattr(importlib, "import_module", import_module)
    app = typer.Typer()
    ModelShowCommand().register(app)

    result = CliRunner().invoke(app, ["app.models.User"])

    assert result.exit_code == 0
    assert "Model:   _UserModel" in result.stdout
    assert "Table:   users" in result.stdout
    assert "Hidden:  ['password']" in result.stdout
