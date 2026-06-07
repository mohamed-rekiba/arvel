"""Auto-register every known ``ArvelSettings`` subclass as a singleton."""

from __future__ import annotations

import os
import warnings
from typing import ClassVar

from arvel.config.errors import ConfigError
from arvel.config.registry import registered_configs
from arvel.config.repository import Config
from arvel.config.settings import ArvelSettings
from arvel.console._subsystem import CliSubsystem
from arvel.providers.service_provider import ServiceProvider


def _warn_unmatched(cls: type[ArvelSettings]) -> None:
    """Emit a UserWarning for env vars that share a settings prefix but map to no field.

    pydantic-settings silently ignores unknown vars when extra="ignore". This
    catches the common typo pattern (e.g. APP_TIEMZONE instead of APP_TIMEZONE)
    without breaking existing deployments.

    Only the first double-underscore segment is checked to avoid false positives
    on nested keys like DB_POOL_SIZE.
    """
    prefix: str = (cls.model_config.get("env_prefix") or "").upper()
    if not prefix:
        return
    known = {f.upper() for f in cls.model_fields}
    for key in os.environ:
        bare = key.upper()
        if bare.startswith(prefix):
            first_segment = bare[len(prefix) :].split("__")[0]
            if first_segment and first_segment not in known:
                warnings.warn(
                    f"{key!r} starts with prefix {prefix!r} for "
                    f"{cls.__qualname__} but matches no field — possible typo.",
                    UserWarning,
                    stacklevel=2,
                )


class ConfigServiceProvider(ServiceProvider):
    subsystem: ClassVar[CliSubsystem | None] = CliSubsystem.CONFIG

    def register(self) -> None:
        Config.bind(self.app.container)
        for cls in registered_configs():
            self.app.container.singleton(cls)

    async def boot(self) -> None:
        # Instantiate every registered config now so validation fires at boot, not at first access.
        for cls in registered_configs():
            try:
                self.app.container.make(cls)
            except ConfigError:
                raise
            except Exception as exc:
                # Wrap unrelated errors so the BootError lookup gets a clean ConfigError.
                msg = f"Failed to load {cls.__qualname__}."
                raise ConfigError(msg) from exc
            _warn_unmatched(cls)
