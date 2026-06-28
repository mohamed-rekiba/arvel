"""Coverage — console main() entrypoint branches (doc 13)."""

from __future__ import annotations

import sys

import pytest

from arvel import __version__
from arvel.console import main


def test_main_version_flag(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["arvel", "--version"])
    main()
    assert __version__ in capsys.readouterr().out


def test_main_short_version_flag(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["arvel", "-V"])
    main()
    assert __version__ in capsys.readouterr().out


def test_main_bare_shows_banner(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["arvel"])
    monkeypatch.setenv("NO_COLOR", "1")
    main()
    assert "arvel" in capsys.readouterr().out


def test_main_dispatches_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["arvel", "about"])
    with pytest.raises(SystemExit) as exc:  # typer exits 0 after a command
        main()
    assert exc.value.code == 0
