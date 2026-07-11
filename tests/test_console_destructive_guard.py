"""CLI-001 — the destructive-command guard: refuse in production, prompt on a TTY, require --force
when non-interactive. A scripted run must never silently wipe a database."""

from __future__ import annotations

from typing import Any

import pytest
import typer

from arvel.console.guard import confirm_destructive


class _App:
    """Minimal app stub exposing just ``config("app.env")``."""

    def __init__(self, env: str) -> None:
        self._env = env

    def config(self, key: str, default: Any = None) -> Any:
        return self._env if key == "app.env" else default


class _FakeStdin:
    def __init__(self, is_tty: bool) -> None:
        self._is_tty = is_tty

    def isatty(self) -> bool:
        return self._is_tty


def _set_tty(monkeypatch: pytest.MonkeyPatch, *, is_tty: bool) -> None:
    import sys

    monkeypatch.setattr(sys, "stdin", _FakeStdin(is_tty))


def test_force_bypasses_every_check() -> None:
    # --force proceeds even in production — the explicit operator override
    confirm_destructive(_App("production"), force=True, action="drop all tables")


@pytest.mark.parametrize("env", ["production", "Production", "PRODUCTION", " prod ", "prod"])
def test_production_refuses_without_force(env: str) -> None:
    # the hard production refusal engages regardless of case / surrounding whitespace / "prod"
    with pytest.raises(typer.Exit):
        confirm_destructive(_App(env), force=False, action="drop all tables")


def test_non_interactive_requires_force(monkeypatch: pytest.MonkeyPatch) -> None:
    # no TTY (CI / piped) → refuse rather than block on a prompt nobody can answer
    _set_tty(monkeypatch, is_tty=False)
    with pytest.raises(typer.Exit):
        confirm_destructive(_App("local"), force=False, action="drop all tables")


def test_interactive_prompt_declined_aborts(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_tty(monkeypatch, is_tty=True)
    monkeypatch.setattr(typer, "confirm", lambda *a, **k: False)
    with pytest.raises(typer.Exit):
        confirm_destructive(_App("local"), force=False, action="drop all tables")


def test_interactive_prompt_accepted_proceeds(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_tty(monkeypatch, is_tty=True)
    monkeypatch.setattr(typer, "confirm", lambda *a, **k: True)
    confirm_destructive(_App("local"), force=False, action="drop all tables")  # no raise
