"""Console (doc 13) — installer mode vs project mode, detected via bootstrap/app.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from arvel.console.context import console_mode, in_project
from arvel.console.lazy import LazyGroup


def _make_project(tmp_path: Path) -> None:
    (tmp_path / "bootstrap").mkdir()
    (tmp_path / "bootstrap" / "app.py").write_text("# arvel app\n")


def test_in_project_detection(tmp_path: Path) -> None:
    assert in_project(str(tmp_path)) is False
    assert console_mode(str(tmp_path)) == "installer"
    _make_project(tmp_path)
    assert in_project(str(tmp_path)) is True
    assert console_mode(str(tmp_path)) == "project"


def test_installer_mode_hides_project_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # no bootstrap/app.py → installer mode
    listed = set(LazyGroup(name="arvel").list_commands(None))  # type: ignore[arg-type]
    assert "new" in listed
    assert "about" in listed
    assert "migrate" not in listed  # project command, hidden
    assert "queue:work" not in listed


def test_project_mode_shows_all_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    listed = set(LazyGroup(name="arvel").list_commands(None))  # type: ignore[arg-type]
    assert {"new", "migrate", "queue:work", "make:model", "shell"} <= listed
