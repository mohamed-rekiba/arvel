"""Typed configuration system — pydantic-settings composition."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import types  # noqa: TC003 - needed at runtime for get_type_hints resolution
from pathlib import Path
from typing import Any

from pydantic import SecretStr, ValidationError
from pydantic_settings import BaseSettings

from arvel.app.config import AppSettings
from arvel.foundation.exceptions import ConfigurationError


class ModuleSettings(BaseSettings):
    """Base for module-level config slices.

    Subclasses set model_config with their own env_prefix so that
    DB_HOST maps to DatabaseSettings and CACHE_HOST maps to CacheSettings.
    """

    model_config = {"extra": "ignore"}


_SNAKE_CASE_RE = re.compile(r"(?<!^)(?=[A-Z])")


def resolve_env_files(base_path: Path, app_env: str | None = None) -> list[str]:
    """Build ordered list of .env files to load.

    Loads .env first, then .env.{environment} as an overlay (if it exists).
    Real environment variables always take precedence over both.
    """
    files: list[str] = []
    base_env = base_path / ".env"
    if base_env.exists():
        files.append(str(base_env))

    if app_env:
        overlay = base_path / f".env.{app_env}"
        if overlay.exists():
            files.append(str(overlay))

    return files


def with_env_files[TSettings: BaseSettings](
    settings_cls: type[TSettings],
    env_files: list[str],
    **extra_fields: Any,
) -> TSettings:
    """Instantiate settings class with explicit env file override."""
    env_file_override: tuple[str, ...] | None = tuple(env_files) if env_files else None
    return settings_cls(_env_file=env_file_override, **extra_fields)  # type: ignore[call-arg]


def default_module_settings() -> list[type[ModuleSettings]]:
    """Return framework module settings loaded by default."""
    from arvel.auth.config import AuthSettings
    from arvel.broadcasting.config import BroadcastSettings
    from arvel.cache.config import CacheSettings
    from arvel.data.config import DatabaseSettings
    from arvel.http.config import HttpSettings
    from arvel.lock.config import LockSettings
    from arvel.mail.config import MailSettings
    from arvel.media.config import MediaSettings
    from arvel.notifications.config import NotificationSettings
    from arvel.observability.config import ObservabilitySettings
    from arvel.queue.config import QueueSettings
    from arvel.scheduler.config import SchedulerSettings
    from arvel.security.config import SecuritySettings
    from arvel.session.config import SessionSettings
    from arvel.storage.config import StorageSettings

    return [
        AuthSettings,
        DatabaseSettings,
        HttpSettings,
        ObservabilitySettings,
        SecuritySettings,
        QueueSettings,
        CacheSettings,
        MailSettings,
        NotificationSettings,
        MediaSettings,
        LockSettings,
        SessionSettings,
        SchedulerSettings,
        BroadcastSettings,
        StorageSettings,
    ]


def settings_file_candidates(settings_cls: type[ModuleSettings]) -> list[str]:
    """Return config file candidate stems for a settings class."""
    explicit_name = getattr(settings_cls, "config_name", None)
    if isinstance(explicit_name, str) and explicit_name:
        return [explicit_name]

    stem = settings_cls.__name__
    if stem.endswith("Settings"):
        stem = stem[: -len("Settings")]
    return [_SNAKE_CASE_RE.sub("_", stem).lower()]


def _load_python_module(module_name: str, file_path: Path) -> types.ModuleType | None:
    """Load a Python module from a file path."""
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _settings_env_prefix(settings_cls: type[ModuleSettings]) -> str:
    """Extract env_prefix from a settings class model_config."""
    raw_prefix = settings_cls.model_config.get("env_prefix", "")
    return raw_prefix if isinstance(raw_prefix, str) else ""


def _validate_discovered_settings_class(
    settings_cls: type[ModuleSettings],
    config_file: Path,
) -> None:
    """Validate discovered settings classes before they enter the merge pipeline."""
    module = sys.modules.get(settings_cls.__module__)
    if module is None:
        return

    try:
        settings_cls.model_rebuild(_types_namespace=vars(module))
    except Exception as exc:  # pragma: no cover - defensive reliability guard
        raise ConfigurationError(
            "Configuration error: settings_class in "
            f"config/{config_file.name} could not be initialized ({exc})",
            field="settings_class",
            env_var=f"config/{config_file.name}",
        ) from exc


def _load_project_config_dict(
    base_path: Path,
    settings_cls: type[ModuleSettings],
) -> dict[str, Any]:
    """Load project defaults from config/<module>.py if available."""
    config_dir = base_path / "config"
    if not config_dir.exists():
        return {}

    for stem in settings_file_candidates(settings_cls):
        config_file = config_dir / f"{stem}.py"
        if not config_file.exists():
            continue

        module = _load_python_module(f"project.config.{stem}", config_file)
        if module is None:
            continue

        payload = getattr(module, "config", None)
        if isinstance(payload, dict):
            return payload
        return {}

    return {}


def _discover_project_module_settings(base_path: Path) -> list[type[ModuleSettings]]:
    """Discover custom ModuleSettings classes exported by project config files."""
    config_dir = base_path / "config"
    if not config_dir.exists():
        return []

    discovered: list[type[ModuleSettings]] = []
    for config_file in sorted(config_dir.glob("*.py")):
        if config_file.name == "__init__.py":
            continue

        module = _load_python_module(f"project.config.{config_file.stem}", config_file)
        if module is None:
            continue

        settings_class = getattr(module, "settings_class", None)
        if settings_class is None:
            continue

        # `config/app.py` may export root AppSettings for export symmetry.
        # Root settings are loaded via `_load_root_settings_from_env`, not as a module slice.
        is_root_app_settings = settings_class is AppSettings or (
            config_file.stem == "app"
            and isinstance(settings_class, type)
            and settings_class.__name__ == "AppSettings"
        )
        if is_root_app_settings:
            continue

        if not isinstance(settings_class, type) or not issubclass(settings_class, ModuleSettings):
            raise ConfigurationError(
                "Configuration error: settings_class in "
                f"config/{config_file.name} must subclass ModuleSettings",
                field="settings_class",
                env_var=f"config/{config_file.name}",
            )
        _validate_discovered_settings_class(settings_class, config_file)
        discovered.append(settings_class)

    return discovered


def _merge_module_settings_classes(
    base_classes: list[type[ModuleSettings]],
    discovered_classes: list[type[ModuleSettings]],
) -> list[type[ModuleSettings]]:
    """Merge module settings with project overrides and conflict protection."""
    merged = [*base_classes]
    prefix_to_index: dict[str, int] = {}

    for index, settings_cls in enumerate(merged):
        prefix = _settings_env_prefix(settings_cls)
        if prefix:
            prefix_to_index[prefix] = index

    for discovered_cls in discovered_classes:
        if discovered_cls in merged:
            continue

        prefix = _settings_env_prefix(discovered_cls)
        if not prefix:
            merged.append(discovered_cls)
            continue

        existing_index = prefix_to_index.get(prefix)
        if existing_index is None:
            prefix_to_index[prefix] = len(merged)
            merged.append(discovered_cls)
            continue

        existing_cls = merged[existing_index]
        if existing_cls.__name__ == discovered_cls.__name__:
            merged[existing_index] = discovered_cls
            continue
        if issubclass(discovered_cls, existing_cls):
            merged[existing_index] = discovered_cls
            continue
        if issubclass(existing_cls, discovered_cls):
            continue

        raise ConfigurationError(
            "Configuration error: duplicate env_prefix "
            f"{prefix!r} across settings classes "
            f"{existing_cls.__name__} and {discovered_cls.__name__}",
            field="env_prefix",
            env_var=prefix,
        )
    return merged


def _collect_present_env_vars(env_files: list[str]) -> set[str]:
    """Collect env keys present in os.environ and referenced env files."""
    present = set(os.environ.keys())

    for env_file in env_files:
        path = Path(env_file)
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            normalized = stripped.removeprefix("export ").strip()
            if "=" not in normalized:
                continue
            key, _, _value = normalized.partition("=")
            key_name = key.strip()
            if key_name:
                present.add(key_name)
    return present


def _field_env_var_candidates(
    settings_cls: type[ModuleSettings],
    field_name: str,
) -> set[str]:
    """Return env var names that can populate a given settings field."""
    candidates: set[str] = set()
    prefix = settings_cls.model_config.get("env_prefix", "")
    candidates.add(f"{prefix}{field_name.upper()}")

    field_info = settings_cls.model_fields.get(field_name)
    if field_info is None:
        return candidates

    validation_alias = field_info.validation_alias
    if isinstance(validation_alias, str):
        candidates.add(validation_alias)
        return candidates
    if validation_alias is None:
        return candidates

    choices = getattr(validation_alias, "choices", None)
    if isinstance(choices, (list, tuple)):
        for choice in choices:
            if isinstance(choice, str):
                candidates.add(choice)
    return candidates


def _load_module_settings(
    settings_cls: type[ModuleSettings],
    base_path: Path,
    env_files: list[str],
) -> ModuleSettings:
    """Instantiate and validate a single module settings class."""
    prefix = settings_cls.model_config.get("env_prefix", "")
    try:
        settings_from_env = with_env_files(settings_cls, env_files)
        project_defaults = _load_project_config_dict(base_path, settings_cls)
        if not project_defaults:
            return settings_from_env

        present_env_vars = _collect_present_env_vars(env_files)
        merged_data = settings_from_env.model_dump()
        for field_name in settings_cls.model_fields:
            if field_name not in project_defaults:
                continue
            env_candidates = _field_env_var_candidates(settings_cls, field_name)
            if env_candidates.isdisjoint(present_env_vars):
                merged_data[field_name] = project_defaults[field_name]
        return settings_cls.model_validate(merged_data)
    except ValidationError as e:
        first = e.errors()[0]
        field_name = first["loc"][0] if first["loc"] else "unknown"
        env_var = f"{prefix}{str(field_name).upper()}"
        raise ConfigurationError(
            f"Configuration error: {env_var} — {first['msg']}",
            field=str(field_name),
            env_var=env_var,
        ) from e


def _load_app_config_dict(base_path: Path) -> dict[str, Any]:
    """Load project defaults for AppSettings from ``config/app.py`` if present.

    Supports two patterns:
    - ``settings_class``: an AppSettings subclass with overridden defaults
    - ``config``: a plain dict of field overrides
    """
    config_file = base_path / "config" / "app.py"
    if not config_file.exists():
        return {}
    module = _load_python_module("project.config.app", config_file)
    if module is None:
        return {}

    settings_cls = getattr(module, "settings_class", None)
    if (
        settings_cls is not None
        and isinstance(settings_cls, type)
        and issubclass(settings_cls, AppSettings)
        and settings_cls is not AppSettings
    ):
        instance = settings_cls()
        return instance.model_dump()

    payload = getattr(module, "config", None)
    return payload if isinstance(payload, dict) else {}


def _build_app_settings(
    base_path: Path,
    env_files: list[str],
) -> AppSettings:
    """Construct and validate AppSettings from env files + config/app.py."""
    try:
        settings_from_env = with_env_files(AppSettings, env_files, base_path=base_path)
        project_defaults = _load_app_config_dict(base_path)
        if not project_defaults:
            return settings_from_env

        present_env_vars = _collect_present_env_vars(env_files)
        merged_data = settings_from_env.model_dump()
        for field_name in AppSettings.model_fields:
            if field_name not in project_defaults:
                continue
            if field_name.startswith("app_"):
                env_var = field_name.upper()
            else:
                env_var = f"APP_{field_name.upper()}"
            if env_var in present_env_vars:
                continue
            merged_data[field_name] = project_defaults[field_name]
        return AppSettings.model_validate(merged_data)
    except ValidationError as e:
        first = e.errors()[0]
        field_name = first["loc"][0] if first["loc"] else "unknown"
        env_var = str(field_name).upper()
        raise ConfigurationError(
            f"Configuration error: {env_var} — {first['msg']}",
            field=str(field_name),
            env_var=env_var,
        ) from e


def _load_cached_root_settings(
    base_path: Path,
    cache_path: Path | None,
    *,
    testing: bool,
) -> AppSettings | None:
    """Load root settings from cache if available and valid."""
    if cache_path is None or not cache_path.exists():
        return None

    try:
        data = json.loads(cache_path.read_text())
        config = AppSettings(**data)
        config.base_path = base_path
        if testing:
            config.app_env = "testing"
        return config
    except json.JSONDecodeError, ValidationError:
        return None


def _load_root_settings_from_env(base_path: Path, *, testing: bool) -> AppSettings:
    """Load root settings from layered env files."""
    env_files = resolve_env_files(base_path)
    config = _build_app_settings(base_path, env_files)
    if testing:
        config.app_env = "testing"

    overlay_files = resolve_env_files(base_path, app_env=config.app_env)
    if len(overlay_files) > len(env_files):
        config = _build_app_settings(base_path, overlay_files)
        if testing:
            config.app_env = "testing"

    return config


async def load_config(
    base_path: Path,
    *,
    cache_path: Path | None = None,
    extra_settings: list[type[ModuleSettings]] | None = None,
    testing: bool = False,
) -> AppSettings:
    """Load and validate application configuration.

    Environment file layering (Laravel-style):
      1. .env (base)
      2. .env.{app_env} overlay (e.g. .env.testing) if it exists
      3. Real environment variables (highest precedence)

    When ``testing=True``, app_env is forced to "testing" and .env.testing
    is loaded as an overlay (if it exists) — no os.environ mutation needed.

    Only root AppSettings are cached to disk. Module settings are always
    loaded from environment variables, even on a cached boot.

    Raises:
        ConfigurationError: If a required env var is missing or invalid.
    """
    config = _load_cached_root_settings(base_path, cache_path, testing=testing)
    if config is None:
        config = _load_root_settings_from_env(base_path, testing=testing)

    env_files_for_modules = resolve_env_files(base_path, app_env=config.app_env)

    if extra_settings is None:
        default_settings = default_module_settings()
        discovered_settings = _discover_project_module_settings(base_path)
        extra_settings = _merge_module_settings_classes(default_settings, discovered_settings)

    if extra_settings:
        for settings_cls in extra_settings:
            instance = _load_module_settings(
                settings_cls,
                base_path=base_path,
                env_files=env_files_for_modules,
            )
            config._module_settings[settings_cls] = instance

    return config


async def cache_config(config: AppSettings, cache_path: Path) -> None:
    """Serialize root config to a file for faster subsequent boots.

    Only root AppSettings fields are cached. Secret values are excluded
    so they're always reloaded from environment. Module settings are
    never cached — they're re-validated from env on every boot.
    """
    data = {}
    for field_name, _field_info in type(config).model_fields.items():
        value = getattr(config, field_name)
        if isinstance(value, SecretStr):
            continue
        if isinstance(value, Path):
            data[field_name] = str(value)
        else:
            data[field_name] = value
    cache_path.write_text(json.dumps(data))  # noqa: ASYNC240


def get_module_settings[TModuleSettings: ModuleSettings](
    config: AppSettings,
    settings_type: type[TModuleSettings],
) -> TModuleSettings:
    """Retrieve a module settings slice from this config instance."""
    result = config._module_settings.get(settings_type)
    if result is None:
        raise ConfigurationError(
            f"Module settings {settings_type.__name__} not loaded — "
            f"pass it to load_config(extra_settings=[{settings_type.__name__}])",
            field=settings_type.__name__,
        )
    if not isinstance(result, settings_type):
        raise ConfigurationError(
            f"Loaded module settings type mismatch for {settings_type.__name__}",
            field=settings_type.__name__,
        )
    return result
