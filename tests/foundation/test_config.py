"""Tests for Typed Configuration System — Story 4.

FR-012: Module settings validated and provided via container
FR-013: Missing required env var fails with name
FR-014: .env loaded, real env takes precedence
FR-015: Module config uses own env_prefix
FR-016: Config cache serialization
NFR-002: Cached boot < 100ms
NFR-005: Secrets never logged/printed
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, ClassVar

import pytest

if TYPE_CHECKING:
    from pathlib import Path
from pydantic import SecretStr

from arvel.foundation.config import AppSettings, ModuleSettings, cache_config, load_config
from arvel.foundation.exceptions import ConfigurationError


class DatabaseSettings(ModuleSettings):
    host: str
    port: int = 5432
    password: SecretStr = SecretStr("")

    model_config: ClassVar[dict[str, str]] = {"env_prefix": "DB_", "extra": "ignore"}


class CacheSettings(ModuleSettings):
    host: str = "localhost"
    port: int = 6379

    model_config: ClassVar[dict[str, str]] = {"env_prefix": "CACHE_", "extra": "ignore"}


class TestModuleSettingsValidation:
    """FR-012: Module settings validated at startup."""

    async def test_valid_settings_loaded(self, tmp_project: Path) -> None:
        (tmp_project / ".env").write_text("APP_NAME=Test\nDB_HOST=localhost\n")
        config = await load_config(tmp_project, extra_settings=[DatabaseSettings])
        assert config is not None

    async def test_settings_available_through_container(self, tmp_project: Path) -> None:
        (tmp_project / ".env").write_text("APP_NAME=Test\nDB_HOST=localhost\n")
        config = await load_config(tmp_project, extra_settings=[DatabaseSettings])
        from arvel.foundation.config import get_module_settings

        db = get_module_settings(config, DatabaseSettings)
        assert db.host == "localhost"
        assert db.port == 5432


class TestMissingRequiredEnvVar:
    """FR-013: Missing required env var names the variable."""

    async def test_missing_required_raises_with_var_name(self, tmp_project: Path) -> None:
        (tmp_project / ".env").write_text("APP_NAME=Test\n")
        with pytest.raises(ConfigurationError) as exc_info:
            await load_config(tmp_project, extra_settings=[DatabaseSettings])
        assert "DB_HOST" in str(exc_info.value)


class TestDotEnvPrecedence:
    """FR-014: .env loaded, real env vars take precedence."""

    async def test_env_file_values_loaded(self, tmp_project: Path, clean_env: None) -> None:
        (tmp_project / ".env").write_text("APP_NAME=FromFile\n")
        config = await load_config(tmp_project)
        assert config.app_name == "FromFile"

    async def test_real_env_overrides_file(
        self, tmp_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_project / ".env").write_text("APP_NAME=FromFile\n")
        monkeypatch.setenv("APP_NAME", "FromEnv")
        config = await load_config(tmp_project)
        assert config.app_name == "FromEnv"


class TestEnvPrefixIsolation:
    """FR-015: Each module config uses its own env_prefix."""

    async def test_prefixed_settings_dont_collide(self, tmp_project: Path) -> None:
        (tmp_project / ".env").write_text(
            "APP_NAME=Test\nDB_HOST=db-server\nCACHE_HOST=cache-server\n"
        )
        config = await load_config(tmp_project, extra_settings=[DatabaseSettings, CacheSettings])
        from arvel.foundation.config import get_module_settings

        db = get_module_settings(config, DatabaseSettings)
        cache = get_module_settings(config, CacheSettings)

        assert db.host == "db-server"
        assert cache.host == "cache-server"


class TestConfigCache:
    """FR-016: Config cache serialization."""

    async def test_cache_and_reload(self, tmp_project: Path, clean_env: None) -> None:
        (tmp_project / ".env").write_text("APP_NAME=CacheTest\n")
        config = await load_config(tmp_project)

        cache_path = tmp_project / ".config_cache"
        await cache_config(config, cache_path)
        assert cache_path.exists()

        cached = await load_config(tmp_project, cache_path=cache_path)
        assert cached.app_name == "CacheTest"

    async def test_cached_boot_under_100ms(self, tmp_project: Path) -> None:
        (tmp_project / ".env").write_text("APP_NAME=PerfTest\n")
        config = await load_config(tmp_project)

        cache_path = tmp_project / ".config_cache"
        await cache_config(config, cache_path)

        start = time.perf_counter()
        await load_config(tmp_project, cache_path=cache_path)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 100, f"Cached load took {elapsed_ms:.0f}ms, expected < 100ms"

    async def test_cached_boot_still_loads_module_settings(self, tmp_project: Path) -> None:
        (tmp_project / ".env").write_text("APP_NAME=CacheTest\nDB_HOST=db-host\n")
        config = await load_config(tmp_project, extra_settings=[DatabaseSettings])
        cache_path = tmp_project / ".config_cache"
        await cache_config(config, cache_path)

        cached = await load_config(
            tmp_project, cache_path=cache_path, extra_settings=[DatabaseSettings]
        )
        from arvel.foundation.config import get_module_settings

        db = get_module_settings(cached, DatabaseSettings)
        assert db.host == "db-host"


class TestSecretRedaction:
    """NFR-005: Secrets never exposed in config dump."""

    def test_secret_str_not_in_repr(self) -> None:
        settings = DatabaseSettings(host="localhost", password=SecretStr("s3cret"))
        text = repr(settings)
        assert "s3cret" not in text

    def test_secret_str_not_in_model_dump(self) -> None:
        settings = DatabaseSettings(host="localhost", password=SecretStr("s3cret"))
        dumped = settings.model_dump()
        password_val = dumped.get("password")
        assert password_val != "s3cret" or password_val is None


class TestAppSettingsDefaults:
    """AppSettings default values."""

    def test_defaults(self, clean_env: None) -> None:
        settings = AppSettings()
        assert settings.app_name == "Arvel"
        assert settings.app_env == "development"
        assert settings.app_debug is False


class TestModuleSettingsIsolation:
    """Module settings belong to the config instance, not a global."""

    async def test_two_configs_have_independent_module_settings(self, tmp_project: Path) -> None:
        (tmp_project / ".env").write_text("APP_NAME=A\nDB_HOST=host-a\n")
        config_a = await load_config(tmp_project, extra_settings=[DatabaseSettings])

        (tmp_project / ".env").write_text("APP_NAME=B\nDB_HOST=host-b\n")
        config_b = await load_config(tmp_project, extra_settings=[DatabaseSettings])

        from arvel.foundation.config import get_module_settings

        assert get_module_settings(config_a, DatabaseSettings).host == "host-a"
        assert get_module_settings(config_b, DatabaseSettings).host == "host-b"


class TestEnvFileLayering:
    """Environment-specific .env file overlay (Laravel-style)."""

    async def test_env_testing_overlay(self, tmp_project: Path) -> None:
        (tmp_project / ".env").write_text("APP_NAME=Base\nAPP_DEBUG=false\n")
        (tmp_project / ".env.testing").write_text("APP_DEBUG=true\n")
        config = await load_config(tmp_project, testing=True)
        assert config.app_env == "testing"
        assert config.app_debug is True

    async def test_base_env_used_when_no_overlay(self, tmp_project: Path, clean_env: None) -> None:
        (tmp_project / ".env").write_text("APP_NAME=Base\nAPP_DEBUG=false\n")
        config = await load_config(tmp_project)
        assert config.app_debug is False

    async def test_real_env_overrides_overlay(
        self, tmp_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_project / ".env").write_text("APP_NAME=Base\n")
        (tmp_project / ".env.testing").write_text("APP_NAME=FromOverlay\n")
        monkeypatch.setenv("APP_NAME", "FromRealEnv")
        config = await load_config(tmp_project, testing=True)
        assert config.app_name == "FromRealEnv"


class FooSettings(ModuleSettings):
    host: str = "framework-default"
    port: int = 1234

    model_config: ClassVar[dict[str, str]] = {"env_prefix": "FOO_", "extra": "ignore"}


class TestProjectConfigMerging:
    """Project config/*.py defaults are merged with env as higher priority."""

    async def test_project_config_overrides_framework_defaults(self, tmp_project: Path) -> None:
        (tmp_project / ".env").write_text("APP_NAME=Merged\n")
        config_dir = tmp_project / "config"
        config_dir.mkdir()
        (config_dir / "foo.py").write_text('config = {"host": "project", "port": 7777}\n')

        config = await load_config(tmp_project, extra_settings=[FooSettings])
        from arvel.foundation.config import get_module_settings

        foo = get_module_settings(config, FooSettings)
        assert foo.host == "project"
        assert foo.port == 7777

    async def test_env_overrides_project_config_values(self, tmp_project: Path) -> None:
        (tmp_project / ".env").write_text("APP_NAME=Merged\nFOO_PORT=8888\n")
        config_dir = tmp_project / "config"
        config_dir.mkdir()
        (config_dir / "foo.py").write_text('config = {"host": "project", "port": 7777}\n')

        config = await load_config(tmp_project, extra_settings=[FooSettings])
        from arvel.foundation.config import get_module_settings

        foo = get_module_settings(config, FooSettings)
        assert foo.host == "project"
        assert foo.port == 8888


class TestProjectSettingsAutodiscovery:
    """Custom settings classes are auto-discovered from project config files."""

    async def test_discovers_project_settings_class_and_loads_env(self, tmp_project: Path) -> None:
        (tmp_project / ".env").write_text(
            "APP_NAME=Autodiscovery\nCUSTOM_FEATURE_TIMEOUT_SECONDS=9\n"
        )
        config_dir = tmp_project / "config"
        config_dir.mkdir()
        (config_dir / "custom_feature.py").write_text(
            "from __future__ import annotations\n\n"
            "from typing import ClassVar\n\n"
            "from arvel.foundation.config import ModuleSettings\n\n"
            "class CustomFeatureSettings(ModuleSettings):\n"
            "    enabled: bool = False\n"
            "    timeout_seconds: int = 5\n\n"
            '    model_config: ClassVar[dict[str, str]] = {"env_prefix": "CUSTOM_FEATURE_", '
            '"extra": "ignore"}\n\n'
            "settings_class = CustomFeatureSettings\n"
            'config = {"enabled": True, "timeout_seconds": 3}\n'
        )

        config = await load_config(tmp_project)
        discovered_instance = next(
            (
                settings
                for settings_type, settings in config._module_settings.items()
                if settings_type.__name__ == "CustomFeatureSettings"
            ),
            None,
        )
        assert discovered_instance is not None
        discovered_data = discovered_instance.model_dump()
        assert discovered_data.get("enabled") is True
        assert discovered_data.get("timeout_seconds") == 9

    async def test_invalid_project_settings_class_raises(self, tmp_project: Path) -> None:
        (tmp_project / ".env").write_text("APP_NAME=Autodiscovery\n")
        config_dir = tmp_project / "config"
        config_dir.mkdir()
        (config_dir / "custom_feature.py").write_text(
            'settings_class = object\nconfig = {"enabled": True}\n'
        )

        with pytest.raises(ConfigurationError, match="must subclass ModuleSettings"):
            await load_config(tmp_project)

    async def test_app_settings_class_in_project_config_is_ignored(self, tmp_project: Path) -> None:
        (tmp_project / ".env").write_text("APP_NAME=Autodiscovery\n")
        config_dir = tmp_project / "config"
        config_dir.mkdir()
        (config_dir / "app.py").write_text(
            "from arvel.app.config import AppSettings\nsettings_class = AppSettings\n"
        )

        config = await load_config(tmp_project)
        assert config.app_name == "Autodiscovery"

    async def test_project_local_app_settings_class_is_ignored(self, tmp_project: Path) -> None:
        (tmp_project / ".env").write_text("APP_NAME=Autodiscovery\n")
        config_dir = tmp_project / "config"
        config_dir.mkdir()
        (config_dir / "app.py").write_text(
            "from __future__ import annotations\n\n"
            "from pathlib import Path\n"
            "from pydantic import SecretStr\n"
            "from pydantic_settings import BaseSettings, SettingsConfigDict\n\n"
            "class AppSettings(BaseSettings):\n"
            "    app_name: str = 'Arvel'\n"
            "    app_env: str = 'development'\n"
            "    app_debug: bool = False\n"
            "    app_key: SecretStr = SecretStr('')\n"
            "    base_path: Path = Path()\n"
            "    model_config = SettingsConfigDict(extra='ignore')\n\n"
            "settings_class = AppSettings\n"
        )

        config = await load_config(tmp_project)
        assert config.app_name == "Autodiscovery"

    async def test_discovered_subclass_overrides_default_module_by_env_prefix(
        self, tmp_project: Path
    ) -> None:
        (tmp_project / ".env").write_text("APP_NAME=Autodiscovery\n")
        config_dir = tmp_project / "config"
        config_dir.mkdir()
        (config_dir / "database.py").write_text(
            "from __future__ import annotations\n\n"
            "from typing import ClassVar\n\n"
            "from arvel.data.config import DatabaseSettings as BaseDatabaseSettings\n\n"
            "class DatabaseSettings(BaseDatabaseSettings):\n"
            '    config_name: ClassVar[str] = "database"\n'
            '    database: str = "database/override.sqlite"\n\n'
            "settings_class = DatabaseSettings\n"
        )

        config = await load_config(tmp_project)
        from arvel.data.config import DatabaseSettings as FrameworkDatabaseSettings

        db_settings = next(
            (
                settings
                for settings_type, settings in config._module_settings.items()
                if issubclass(settings_type, FrameworkDatabaseSettings)
            ),
            None,
        )
        assert db_settings is not None
        assert db_settings.model_dump().get("database") == "database/override.sqlite"

        db_prefix_types = [
            settings_type
            for settings_type in config._module_settings
            if settings_type.model_config.get("env_prefix") == "DB_"
        ]
        assert len(db_prefix_types) == 1

    async def test_conflicting_env_prefix_between_default_and_discovered_raises(
        self, tmp_project: Path
    ) -> None:
        (tmp_project / ".env").write_text("APP_NAME=Autodiscovery\n")
        config_dir = tmp_project / "config"
        config_dir.mkdir()
        (config_dir / "db_shadow.py").write_text(
            "from __future__ import annotations\n\n"
            "from typing import ClassVar\n\n"
            "from arvel.foundation.config import ModuleSettings\n\n"
            "class DbShadowSettings(ModuleSettings):\n"
            "    fake: str = 'x'\n"
            "    model_config: ClassVar[dict[str, str]] = {\n"
            '        "env_prefix": "DB_",\n'
            '        "extra": "ignore",\n'
            "    }\n\n"
            "settings_class = DbShadowSettings\n"
        )

        with pytest.raises(ConfigurationError, match="duplicate env_prefix"):
            await load_config(tmp_project)

    async def test_same_name_same_prefix_discovered_class_overrides_default(
        self, tmp_project: Path
    ) -> None:
        (tmp_project / ".env").write_text("APP_NAME=Autodiscovery\n")
        config_dir = tmp_project / "config"
        config_dir.mkdir()
        (config_dir / "auth.py").write_text(
            "from __future__ import annotations\n\n"
            "from typing import ClassVar\n\n"
            "from pydantic_settings import SettingsConfigDict\n"
            "from arvel.foundation.config import ModuleSettings\n\n"
            "class AuthSettings(ModuleSettings):\n"
            "    model_config = SettingsConfigDict(env_prefix='AUTH_', extra='ignore')\n"
            "    config_name: ClassVar[str] = 'auth'\n"
            "    default_guard: str = 'api'\n\n"
            "settings_class = AuthSettings\n"
        )

        config = await load_config(tmp_project)
        discovered_auth = next(
            (
                settings
                for settings_type, settings in config._module_settings.items()
                if settings_type.__name__ == "AuthSettings"
                and settings_type.model_config.get("env_prefix") == "AUTH_"
            ),
            None,
        )
        assert discovered_auth is not None
