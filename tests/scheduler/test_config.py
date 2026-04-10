"""Tests for SchedulerSettings — config validation, defaults, env overrides."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.scheduler.config import SchedulerSettings

if TYPE_CHECKING:
    import pytest


class TestSchedulerSettingsDefaults:
    """FR-013: SchedulerSettings defaults."""

    def test_default_enabled(self, clean_env: None) -> None:
        settings = SchedulerSettings()
        assert settings.enabled is True

    def test_default_timezone(self, clean_env: None) -> None:
        settings = SchedulerSettings()
        assert settings.timezone == "UTC"

    def test_default_lock_backend(self, clean_env: None) -> None:
        settings = SchedulerSettings()
        assert settings.lock_backend == "memory"


class TestSchedulerSettingsEnvOverrides:
    """FR-013: Env vars override defaults."""

    def test_env_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCHEDULER_ENABLED", "false")
        settings = SchedulerSettings()
        assert settings.enabled is False

    def test_env_timezone(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCHEDULER_TIMEZONE", "US/Eastern")
        settings = SchedulerSettings()
        assert settings.timezone == "US/Eastern"

    def test_env_lock_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCHEDULER_LOCK_BACKEND", "null")
        settings = SchedulerSettings()
        assert settings.lock_backend == "null"
