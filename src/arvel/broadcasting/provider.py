"""BroadcastServiceProvider — wires broadcasting into the DI container."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from arvel.broadcasting.authorizer import ChannelAuthorizer
from arvel.broadcasting.config import BroadcastSettings
from arvel.broadcasting.contracts import BroadcastContract
from arvel.foundation.config import get_module_settings
from arvel.foundation.container import Scope
from arvel.foundation.provider import ServiceProvider

if TYPE_CHECKING:
    from arvel.app.config import AppSettings
    from arvel.foundation.application import Application
    from arvel.foundation.container import ContainerBuilder


class BroadcastServiceProvider(ServiceProvider):
    """Registers broadcasting contract and channel authorizer."""

    priority = 15

    _settings: BroadcastSettings | None

    def __init__(self) -> None:
        super().__init__()
        self._settings = None

    def configure(self, config: AppSettings) -> None:
        with contextlib.suppress(Exception):
            self._settings = get_module_settings(config, BroadcastSettings)

    def _get_settings(self) -> BroadcastSettings:
        if self._settings is not None:
            return self._settings
        return BroadcastSettings()

    def _make_broadcaster(self) -> BroadcastContract:
        settings = self._get_settings()
        if settings.driver == "memory":
            from arvel.broadcasting.drivers.memory_driver import MemoryBroadcaster

            return MemoryBroadcaster()
        if settings.driver == "log":
            from arvel.broadcasting.drivers.log_driver import LogBroadcaster

            return LogBroadcaster()
        if settings.driver == "redis":
            import redis.asyncio as aioredis

            from arvel.broadcasting.drivers.redis_driver import RedisBroadcaster

            client = aioredis.from_url(settings.redis_url)
            return RedisBroadcaster(client=client, prefix=settings.redis_prefix)  # ty: ignore[invalid-argument-type]
        if settings.driver == "null":
            from arvel.broadcasting.drivers.null_driver import NullBroadcaster

            return NullBroadcaster()

        from arvel.foundation.exceptions import ConfigurationError

        raise ConfigurationError(f"Unsupported BROADCAST_DRIVER '{settings.driver}'")

    async def register(self, container: ContainerBuilder) -> None:
        container.provide_factory(BroadcastContract, self._make_broadcaster, scope=Scope.APP)
        container.provide_value(ChannelAuthorizer, ChannelAuthorizer())

    async def boot(self, app: Application) -> None:
        pass
