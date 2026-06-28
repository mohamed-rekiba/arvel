"""Coverage — console banner + built-in commands (doc 13)."""

from __future__ import annotations

import os
import sys

import pytest
from typer.testing import CliRunner

from arvel.console import build_cli
from arvel.console.banner import _gradient, _lerp, print_banner

runner = CliRunner()


def test_lerp_and_gradient() -> None:
    assert _lerp((0, 0, 0), (10, 20, 30), 0.5) == (5, 10, 15)
    rendered = _gradient("AB", 2)
    assert "\x1b[38;2;" in rendered  # truecolor ANSI
    assert rendered.endswith("\x1b[0m")


def test_print_banner_plain(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    print_banner("9.9.9")
    assert "arvel 9.9.9" in capsys.readouterr().out


def test_print_banner_full_color(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("ARVEL_NO_BANNER", raising=False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(os, "get_terminal_size", lambda *a: os.terminal_size((100, 24)))
    print_banner("1.0.0")
    assert "\x1b[38;2;" in capsys.readouterr().out  # gradient art rendered


def test_print_banner_narrow(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(os, "get_terminal_size", lambda *a: os.terminal_size((40, 24)))
    print_banner("2.0.0")
    out = capsys.readouterr().out
    assert "v2.0.0" in out  # narrow compact banner with plain version suffix
    assert "\x1b[38;2;" in out  # still gradient-rendered


@pytest.mark.parametrize(
    ("args", "expect"),
    [
        (["about"], "arvel"),
        (["extras"], "extras"),
        (["down"], "maintenance"),
        (["up"], "live"),
    ],
)
def test_builtin_commands(args: list[str], expect: str) -> None:
    result = runner.invoke(build_cli(), args)
    assert result.exit_code == 0
    assert expect in result.output
