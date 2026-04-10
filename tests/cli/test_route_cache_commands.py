"""Tests for FR-020-05: Route Cache (arvel route cache / clear).

All tests are written BEFORE implementation (QA-Pre / Stage 3a).
They must compile but FAIL until the implementation is complete.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from arvel.cli.app import app

if TYPE_CHECKING:
    import pytest

runner = CliRunner()


class TestRouteCacheCommandRegistered:
    """Route cache/clear commands are accessible."""

    def test_route_cache_help(self) -> None:
        result = runner.invoke(app, ["route", "cache", "--help"])
        assert result.exit_code == 0

    def test_route_clear_help(self) -> None:
        result = runner.invoke(app, ["route", "clear", "--help"])
        assert result.exit_code == 0


class TestRouteCache:
    """FR-020-05.1: arvel route cache serializes route table to JSON."""

    def test_route_cache_creates_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        (tmp_path / "bootstrap" / "cache").mkdir(parents=True, exist_ok=True)

        result = runner.invoke(app, ["route", "cache", "--app-dir", str(tmp_path)])
        assert result.exit_code == 0

        cache_file = tmp_path / "bootstrap" / "cache" / "routes.json"
        assert cache_file.exists()

    def test_route_cache_is_valid_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        (tmp_path / "bootstrap" / "cache").mkdir(parents=True, exist_ok=True)

        runner.invoke(app, ["route", "cache", "--app-dir", str(tmp_path)])

        cache_file = tmp_path / "bootstrap" / "cache" / "routes.json"
        data = json.loads(cache_file.read_text())
        assert isinstance(data, list)

    def test_route_cache_entry_structure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Each entry should have path, methods, name, middleware — no source code."""
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        (tmp_path / "bootstrap" / "cache").mkdir(parents=True, exist_ok=True)

        # Create a dummy route file
        routes_dir = tmp_path / "routes"
        routes_dir.mkdir(parents=True, exist_ok=True)
        (routes_dir / "demo.py").write_text(
            "from arvel.http.router import Router\n"
            "router = Router()\n"
            "@router.get('/demo', name='demo.index')\n"
            "async def index(): return {'ok': True}\n"
        )

        runner.invoke(app, ["route", "cache", "--app-dir", str(tmp_path)])

        cache_file = tmp_path / "bootstrap" / "cache" / "routes.json"
        data = json.loads(cache_file.read_text())
        assert len(data) >= 1
        entry = data[0]
        assert "path" in entry
        assert "methods" in entry
        assert "name" in entry


class TestRouteCacheNoInternals:
    """FR-020-05.4: Cache doesn't contain middleware source or internal paths."""

    def test_route_cache_no_source_code(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        (tmp_path / "bootstrap" / "cache").mkdir(parents=True, exist_ok=True)

        runner.invoke(app, ["route", "cache", "--app-dir", str(tmp_path)])

        cache_file = tmp_path / "bootstrap" / "cache" / "routes.json"
        content = cache_file.read_text()
        assert "def " not in content
        assert "class " not in content
        assert "import " not in content


class TestRouteClear:
    """FR-020-05.3: arvel route clear deletes the cache."""

    def test_route_clear_removes_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        cache_dir = tmp_path / "bootstrap" / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "routes.json").write_text("[]")

        result = runner.invoke(app, ["route", "clear"])
        assert result.exit_code == 0
        assert not (cache_dir / "routes.json").exists()

    def test_route_clear_when_no_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        (tmp_path / "bootstrap" / "cache").mkdir(parents=True, exist_ok=True)

        result = runner.invoke(app, ["route", "clear"])
        assert result.exit_code == 0


class TestRouteCacheRegeneration:
    """FR-020-05.5: Re-running route cache regenerates the file."""

    def test_route_cache_regenerates_on_rerun(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        cache_dir = tmp_path / "bootstrap" / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        runner.invoke(app, ["route", "cache", "--app-dir", str(tmp_path)])
        cache_file = cache_dir / "routes.json"
        first_content = cache_file.read_text()

        runner.invoke(app, ["route", "cache", "--app-dir", str(tmp_path)])
        second_content = cache_file.read_text()

        assert first_content == second_content
        assert cache_file.exists()
