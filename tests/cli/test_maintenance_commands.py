"""Tests for FR-020-03: Maintenance Mode (arvel down / arvel up).

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


class TestMaintenanceCommandsRegistered:
    """Maintenance commands are accessible in the CLI."""

    def test_down_help(self) -> None:
        result = runner.invoke(app, ["down", "--help"])
        assert result.exit_code == 0
        assert "maintenance" in result.output.lower() or "down" in result.output.lower()

    def test_up_help(self) -> None:
        result = runner.invoke(app, ["up", "--help"])
        assert result.exit_code == 0


class TestDownCommand:
    """FR-020-03.1: arvel down creates maintenance signal file."""

    def test_down_creates_maintenance_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        (tmp_path / "bootstrap").mkdir(parents=True, exist_ok=True)

        result = runner.invoke(app, ["down"])
        assert result.exit_code == 0

        maint_file = tmp_path / "bootstrap" / "maintenance.json"
        assert maint_file.exists()

    def test_down_is_idempotent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        (tmp_path / "bootstrap").mkdir(parents=True, exist_ok=True)

        runner.invoke(app, ["down"])
        result = runner.invoke(app, ["down"])
        assert result.exit_code == 0


class TestDownWithBypassSecret:
    """FR-020-03.2 / FR-020-03.3: Bypass secret is hashed with SHA-256."""

    def test_down_with_secret_stores_hash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        (tmp_path / "bootstrap").mkdir(parents=True, exist_ok=True)

        result = runner.invoke(app, ["down", "--secret", "my-bypass-token"])
        assert result.exit_code == 0

        maint_file = tmp_path / "bootstrap" / "maintenance.json"
        data = json.loads(maint_file.read_text())
        assert "secret_hash" in data
        assert data["secret_hash"] is not None
        assert "my-bypass-token" not in data["secret_hash"]
        assert data["secret_hash"].startswith("sha256:")

    def test_down_without_secret_has_null_hash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        (tmp_path / "bootstrap").mkdir(parents=True, exist_ok=True)

        runner.invoke(app, ["down"])

        maint_file = tmp_path / "bootstrap" / "maintenance.json"
        data = json.loads(maint_file.read_text())
        assert data.get("secret_hash") is None


class TestDownWithIPAllowlist:
    """FR-020-03.4: IP-based bypass for CIDR range."""

    def test_down_with_allow_stores_cidr(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        (tmp_path / "bootstrap").mkdir(parents=True, exist_ok=True)

        result = runner.invoke(app, ["down", "--allow", "192.168.1.0/24"])
        assert result.exit_code == 0

        maint_file = tmp_path / "bootstrap" / "maintenance.json"
        data = json.loads(maint_file.read_text())
        assert "allowed_ips" in data
        assert "192.168.1.0/24" in data["allowed_ips"]

    def test_down_with_invalid_cidr_rejects(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        (tmp_path / "bootstrap").mkdir(parents=True, exist_ok=True)

        result = runner.invoke(app, ["down", "--allow", "not-a-cidr"])
        assert result.exit_code != 0


class TestDownWithRetryAfter:
    """FR-020-03.5: Retry-After header value stored in maintenance file."""

    def test_down_with_retry_stores_seconds(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        (tmp_path / "bootstrap").mkdir(parents=True, exist_ok=True)

        result = runner.invoke(app, ["down", "--retry", "60"])
        assert result.exit_code == 0

        maint_file = tmp_path / "bootstrap" / "maintenance.json"
        data = json.loads(maint_file.read_text())
        assert data["retry_after"] == 60


class TestUpCommand:
    """FR-020-03.6: arvel up removes maintenance file."""

    def test_up_removes_maintenance_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        bootstrap = tmp_path / "bootstrap"
        bootstrap.mkdir(parents=True, exist_ok=True)
        (bootstrap / "maintenance.json").write_text("{}")

        result = runner.invoke(app, ["up"])
        assert result.exit_code == 0
        assert not (bootstrap / "maintenance.json").exists()

    def test_up_when_not_in_maintenance(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        (tmp_path / "bootstrap").mkdir(parents=True, exist_ok=True)

        result = runner.invoke(app, ["up"])
        assert result.exit_code == 0
