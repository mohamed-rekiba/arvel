"""Typed configuration layer (pydantic-settings v2 based)."""

from arvel.config._lookup_registry import ConfigKeyError, config, has, lookup
from arvel.config.cache_config import CacheConfig, CacheDriver
from arvel.config.db_config import DbConfig
from arvel.config.errors import ConfigError, ConfigNotRegisteredError
from arvel.config.no_prefix import NoPrefix
from arvel.config.registry import register, registered_configs
from arvel.config.repository import Config
from arvel.config.session_config import SameSite, SessionConfig, SessionDriver
from arvel.config.settings import ArvelSettings
from arvel.config.storage_config import (
    AzureConfig,
    GcsConfig,
    LocalConfig,
    S3Config,
    StorageConfig,
)

__all__ = [
    "ArvelSettings",
    "AzureConfig",
    "CacheConfig",
    "CacheDriver",
    "Config",
    "ConfigError",
    "ConfigKeyError",
    "ConfigNotRegisteredError",
    "DbConfig",
    "GcsConfig",
    "LocalConfig",
    "NoPrefix",
    "S3Config",
    "SameSite",
    "SessionConfig",
    "SessionDriver",
    "StorageConfig",
    "config",
    "has",
    "lookup",
    "register",
    "registered_configs",
]
