"""Config-related error classes."""

from __future__ import annotations


class ConfigError(Exception):
    """Base class for all arvel.config errors."""


class ConfigNotRegisteredError(ConfigError):
    """Raised when Config.of(cls) is called for a class not bound to the container."""

    def __init__(self, settings_cls: type) -> None:
        self.settings_cls = settings_cls
        super().__init__(
            f"{settings_cls.__qualname__} is not registered. "
            "Either include it in Application.with_config_files([...]) "
            "or container.singleton({name}) it manually.".format(name=settings_cls.__qualname__),
        )
