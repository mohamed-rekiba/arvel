"""Tests for DatabaseSettings configuration.

Covers: SAD-003 D7 — config module for the data layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.data.config import DatabaseSettings
from arvel.foundation.config import ModuleSettings

if TYPE_CHECKING:
    import pytest


class TestDatabaseSettings:
    """DatabaseSettings is a valid ModuleSettings with DB_ prefix."""

    def test_is_module_settings_subclass(self) -> None:
        assert issubclass(DatabaseSettings, ModuleSettings)

    def test_default_url_is_sqlite(self, clean_env: None) -> None:
        settings = DatabaseSettings()
        assert "sqlite" in settings.url

    def test_default_driver_is_sqlite(self, clean_env: None) -> None:
        settings = DatabaseSettings()
        assert settings.driver == "sqlite"

    def test_default_echo_is_false(self, clean_env: None) -> None:
        settings = DatabaseSettings()
        assert settings.echo is False

    def test_default_pool_size(self, clean_env: None) -> None:
        settings = DatabaseSettings()
        assert settings.pool_size == 10

    def test_default_pool_max_overflow(self, clean_env: None) -> None:
        settings = DatabaseSettings()
        assert settings.pool_max_overflow == 5

    def test_default_pool_timeout(self, clean_env: None) -> None:
        settings = DatabaseSettings()
        assert settings.pool_timeout == 30

    def test_default_pool_recycle(self, clean_env: None) -> None:
        settings = DatabaseSettings()
        assert settings.pool_recycle == 3600

    def test_default_pool_pre_ping_is_true(self, clean_env: None) -> None:
        settings = DatabaseSettings()
        assert settings.pool_pre_ping is True

    def test_default_expire_on_commit_is_false(self, clean_env: None) -> None:
        settings = DatabaseSettings()
        assert settings.expire_on_commit is False

    def test_pool_settings_configurable_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DB_POOL_SIZE", "20")
        monkeypatch.setenv("DB_POOL_MAX_OVERFLOW", "10")
        monkeypatch.setenv("DB_POOL_RECYCLE", "1800")
        monkeypatch.setenv("DB_POOL_PRE_PING", "false")
        settings = DatabaseSettings()
        assert settings.pool_size == 20
        assert settings.pool_max_overflow == 10
        assert settings.pool_recycle == 1800
        assert settings.pool_pre_ping is False

    def test_env_prefix_is_db(self) -> None:
        prefix = DatabaseSettings.model_config.get("env_prefix", "")
        assert prefix == "DB_"

    def test_driver_can_use_db_driver(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DB_DRIVER", "pgsql")
        settings = DatabaseSettings()
        assert settings.driver == "pgsql"
