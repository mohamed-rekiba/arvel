"""Coverage — console banner + built-in commands (doc 13)."""

from __future__ import annotations

import sys

import pytest
from typer.testing import CliRunner

from arvel.console import build_cli
from arvel.console.banner import print_banner

runner = CliRunner()


def test_print_banner_plain_on_non_tty(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pipe/CI (non-TTY) gets a single clean `arvel <version>` line — no art, no color."""
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False, raising=False)
    print_banner("9.9.9")
    out = capsys.readouterr().out
    assert "arvel 9.9.9" in out
    assert "\x1b[" not in out  # never any ANSI color


def test_print_banner_art_on_tty(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real terminal gets the ASCII art banner + tagline — still no color codes."""
    monkeypatch.delenv("ARVEL_NO_BANNER", raising=False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    print_banner("1.2.3")
    out = capsys.readouterr().out
    assert "(_|" in out  # a distinctive fragment of the ASCII art
    assert "arvel · async-first" in out and "v1.2.3" in out
    assert "\x1b[" not in out  # plain — no ANSI


def test_print_banner_suppressed_by_env(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.setenv("ARVEL_NO_BANNER", "1")
    print_banner("3.0.0")
    assert capsys.readouterr().out.strip() == "arvel 3.0.0"


@pytest.mark.parametrize(
    ("args", "expect"),
    [
        (["about"], "arvel"),
        (["extras"], "extras"),
        # down/up now require the project app (the flag must land in the APP's cache store) —
        # covered with a bound app in test_maintenance_mode.test_down_up_cli_uses_the_app_bound_cache
    ],
)
def test_builtin_commands(args: list[str], expect: str) -> None:
    result = runner.invoke(build_cli(), args)
    assert result.exit_code == 0
    assert expect in result.output
