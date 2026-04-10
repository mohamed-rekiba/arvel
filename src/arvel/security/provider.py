"""SecurityProvider — wires hashing contracts from security settings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.foundation.container import Scope
from arvel.foundation.exceptions import ConfigurationError
from arvel.foundation.provider import ServiceProvider
from arvel.security.config import SecuritySettings
from arvel.security.contracts import HasherContract
from arvel.security.hashing import Argon2Hasher, BcryptHasher

if TYPE_CHECKING:
    from arvel.foundation.container import ContainerBuilder


def _make_hasher() -> HasherContract:
    settings = SecuritySettings()
    if settings.hash_driver == "bcrypt":
        return BcryptHasher(rounds=settings.bcrypt_rounds)
    if settings.hash_driver == "argon2":
        return Argon2Hasher(
            time_cost=settings.argon2_time_cost,
            memory_cost=settings.argon2_memory_cost,
            parallelism=settings.argon2_parallelism,
        )
    raise ConfigurationError(f"Unsupported SECURITY_HASH_DRIVER '{settings.hash_driver}'")


class SecurityProvider(ServiceProvider):
    """Registers core security primitives for dependency injection."""

    priority = 12

    async def register(self, container: ContainerBuilder) -> None:
        container.provide_factory(HasherContract, _make_hasher, scope=Scope.APP)
