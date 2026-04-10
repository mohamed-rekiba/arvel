"""BroadcastServiceProvider — wires broadcasting into the DI container."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.broadcasting.authorizer import ChannelAuthorizer
from arvel.broadcasting.config import BroadcastSettings
from arvel.broadcasting.contracts import BroadcastContract
from arvel.foundation.container import Scope
from arvel.foundation.provider import ServiceProvider

if TYPE_CHECKING:
    from arvel.foundation.application import Application
    from arvel.foundation.container import ContainerBuilder


def _make_broadcaster() -> BroadcastContract:
    settings = BroadcastSettings()
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
        # redis.asyncio.Redis satisfies _AsyncRedisClient (publish + aclose)
        return RedisBroadcaster(client=client, prefix=settings.redis_prefix)  # ty: ignore[invalid-argument-type]
    if settings.driver == "null":
        from arvel.broadcasting.drivers.null_driver import NullBroadcaster

        return NullBroadcaster()

    from arvel.foundation.exceptions import ConfigurationError

    raise ConfigurationError(f"Unsupported BROADCAST_DRIVER '{settings.driver}'")


class BroadcastServiceProvider(ServiceProvider):
    """Registers broadcasting contract and channel authorizer."""

    priority = 15

    async def register(self, container: ContainerBuilder) -> None:
        container.provide_factory(BroadcastContract, _make_broadcaster, scope=Scope.APP)
        container.provide_value(ChannelAuthorizer, ChannelAuthorizer())

    async def boot(self, app: Application) -> None:
        pass
