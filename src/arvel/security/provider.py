"""SecurityProvider — wires hashing contracts from security settings."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from arvel.foundation.config import get_module_settings
from arvel.foundation.container import Scope
from arvel.foundation.exceptions import ConfigurationError
from arvel.foundation.provider import ServiceProvider
from arvel.security.config import SecuritySettings
from arvel.security.contracts import HasherContract
from arvel.security.hashing import Argon2Hasher, BcryptHasher

if TYPE_CHECKING:
    from arvel.app.config import AppSettings
    from arvel.foundation.application import Application
    from arvel.foundation.container import ContainerBuilder


class SecurityProvider(ServiceProvider):
    """Registers core security primitives for dependency injection."""

    priority = 12

    _settings: SecuritySettings | None

    def __init__(self) -> None:
        super().__init__()
        self._settings = None

    def configure(self, config: AppSettings) -> None:
        with contextlib.suppress(Exception):
            self._settings = get_module_settings(config, SecuritySettings)

    def _get_settings(self) -> SecuritySettings:
        if self._settings is not None:
            return self._settings
        return SecuritySettings()

    def _make_hasher(self) -> HasherContract:
        settings = self._get_settings()
        if settings.hash_driver == "bcrypt":
            return BcryptHasher(rounds=settings.bcrypt_rounds)
        if settings.hash_driver == "argon2":
            return Argon2Hasher(
                time_cost=settings.argon2_time_cost,
                memory_cost=settings.argon2_memory_cost,
                parallelism=settings.argon2_parallelism,
            )
        raise ConfigurationError(f"Unsupported SECURITY_HASH_DRIVER '{settings.hash_driver}'")

    async def register(self, container: ContainerBuilder) -> None:
        container.provide_factory(HasherContract, self._make_hasher, scope=Scope.APP)

    async def boot(self, app: Application) -> None:
        pass
