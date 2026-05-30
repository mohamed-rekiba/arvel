"""config:* console command branches."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

import pytest
import typer
from arvel.config import ConfigKeyError
from arvel.console.commands import config_commands
from arvel.console.commands.config_commands import ConfigPublishCommand, ConfigShowCommand
from typer.testing import CliRunner


def test_config_show_prints_json_value(monkeypatch: pytest.MonkeyPatch) -> None:
    def lookup(key: str) -> object:
        return {"key": key}

    monkeypatch.setattr(config_commands, "lookup", lookup)
    app = typer.Typer()
    ConfigShowCommand().register(app)

    result = CliRunner().invoke(app, ["app.name"])

    assert result.exit_code == 0
    assert '"key": "app.name"' in result.stdout


def test_config_show_reports_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    def lookup(key: str) -> object:
        raise ConfigKeyError(key)

    monkeypatch.setattr(config_commands, "lookup", lookup)
    app = typer.Typer()
    ConfigShowCommand().register(app)

    result = CliRunner().invoke(app, ["missing.key"])

    assert result.exit_code == 2
    assert "missing.key" in result.stderr


def test_config_publish_delegates_to_vendor_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str | None, str | None, bool]] = []

    class VendorPublishCommand:
        app: object | None = None

        def publish(self, *, provider: str | None, tag: str | None, force: bool) -> int:
            calls.append((provider, tag, force))
            return 3

    monkeypatch.setattr(config_commands, "VendorPublishCommand", VendorPublishCommand)
    command = ConfigPublishCommand()
    publish = cast(
        "Callable[..., int]",
        object.__getattribute__(command, "_publish"),
    )

    assert publish(provider="Provider", tag=None, force=True) == 3
    assert calls == [("Provider", "config", True)]
