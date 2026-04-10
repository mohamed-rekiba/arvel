"""Tests for arvel publish stubs command."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from typer.testing import CliRunner

if TYPE_CHECKING:
    import pytest

from arvel.cli.app import app

runner = CliRunner()


class TestPublishStubs:
    def test_publish_stubs_help(self) -> None:
        result = runner.invoke(app, ["publish", "--help"])
        assert result.exit_code == 0

    def test_publish_stubs_copies_templates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os

        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

        result = runner.invoke(app, ["publish", "stubs"])
        assert result.exit_code == 0
        assert "Published" in result.output

        stubs_dir = tmp_path / "stubs"
        assert stubs_dir.exists()
        assert (stubs_dir / "model.py.j2").exists()
        assert (stubs_dir / "controller.py.j2").exists()
        assert (stubs_dir / "service.py.j2").exists()

    def test_publish_stubs_skips_existing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os

        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

        stubs_dir = tmp_path / "stubs"
        stubs_dir.mkdir()
        (stubs_dir / "model.py.j2").write_text("custom content")

        result = runner.invoke(app, ["publish", "stubs"])
        assert result.exit_code == 0
        assert "SKIP" in result.output

        assert (stubs_dir / "model.py.j2").read_text() == "custom content"

    def test_publish_stubs_force_overwrites(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os

        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

        stubs_dir = tmp_path / "stubs"
        stubs_dir.mkdir()
        (stubs_dir / "model.py.j2").write_text("custom content")

        result = runner.invoke(app, ["publish", "stubs", "--force"])
        assert result.exit_code == 0
        assert "COPY" in result.output

        assert (stubs_dir / "model.py.j2").read_text() != "custom content"
