"""Tests for cache CLI commands — FR-006-039..041."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import typer
from arvel.console.entrypoint import build_app
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def cli_app() -> typer.Typer:
    return build_app()


@pytest.fixture
def unbind_cache_facade() -> Any:
    from arvel.facades.cache import Cache

    previous = Cache.manager
    Cache.manager = None
    try:
        yield
    finally:
        Cache.manager = previous


class TestCacheClearCommand:
    """FR-006-039 + FR-021-06: ``arvel cache:clear`` is honest about subsystem state.

    Pre-WI-021 these tests asserted exit-0 even when the cache facade was
    unbound — backed by a bare-except swallow that printed a fake
    "Cache cleared." Per NFR-021-04 (CLI exit-code honesty) the swallow is gone:
    without a CacheServiceProvider the command surfaces RuntimeError, which
    Typer maps to a non-zero exit code.
    """

    @pytest.mark.usefixtures("unbind_cache_facade")
    def test_cache_clear_fails_loudly_when_subsystem_unbound(
        self, runner: CliRunner, cli_app: typer.Typer
    ) -> None:
        result = runner.invoke(cli_app, ["cache:clear"])
        assert result.exit_code != 0
        assert "cleared" not in result.output.lower()


class TestCacheForgetCommand:
    """FR-006-040 + FR-021-07: ``arvel cache:forget <key>`` honest about subsystem state."""

    @pytest.mark.usefixtures("unbind_cache_facade")
    def test_cache_forget_fails_loudly_when_subsystem_unbound(
        self, runner: CliRunner, cli_app: typer.Typer
    ) -> None:
        result = runner.invoke(cli_app, ["cache:forget", "some.key"])
        assert result.exit_code != 0


class TestStorageLinkCommand:
    """FR-006-043: arvel storage:link."""

    def test_storage_link_creates_symlink(
        self,
        runner: CliRunner,
        cli_app: typer.Typer,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "public").mkdir()
        (tmp_path / "storage" / "app" / "public").mkdir(parents=True)
        result = runner.invoke(cli_app, ["storage:link"])
        assert result.exit_code == 0
        link = tmp_path / "public" / "storage"
        assert link.exists() or link.is_symlink()

    def test_storage_link_idempotent(
        self,
        runner: CliRunner,
        cli_app: typer.Typer,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "public").mkdir()
        (tmp_path / "storage" / "app" / "public").mkdir(parents=True)
        runner.invoke(cli_app, ["storage:link"])
        # Second call must not raise
        result = runner.invoke(cli_app, ["storage:link"])
        assert result.exit_code == 0
