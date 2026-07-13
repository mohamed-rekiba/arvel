"""arvel.cache.redis — a direct Redis facade.

cashews (``arvel.cache``) covers the *cache* abstraction; this module is the redis-backed store
slice for callers that need Redis itself — raw commands, pipelines/transactions, publish/
subscribe, ``EVAL``. ``RedisManager`` resolves named connections from the ``redis`` config
section (``redis.url`` for the default connection, ``redis.connections.{name}.url`` for others)
into a ``RedisConnection``. Bound as ``redis`` in the container by ``CacheServiceProvider``; the
``Redis`` facade in ``arvel.support.facades`` proxies it. The ``redis`` package is already
required by the cache layer's ``[redis]`` extra (``cashews[redis]``) — imported lazily here too,
so ``import arvel`` stays light (G2), and a missing extra raises ``MissingExtraError``.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

import msgspec

from arvel.kernel import Settings
from arvel.support.manager import MissingExtraError
from arvel.telemetry import span


def _no_connections() -> dict[str, dict[str, Any]]:
    return {}


class RedisSettings(Settings):
    """Typed, validated view over the ``redis`` config section (DR-0016).

    ``url`` is the default connection's DSN; ``connections`` maps name -> ``{"url": ...}`` for
    additional named connections.
    """

    __config_key__ = "redis"
    url: str = "redis://localhost:6379/0"
    connections: dict[str, dict[str, Any]] = msgspec.field(default_factory=_no_connections)


class RedisPipeline:
    """A batch of commands sent as one round trip (``transaction=True`` wraps them in MULTI/EXEC)."""

    def __init__(self, pipe: Any) -> None:
        self._pipe = pipe

    def command(self, name: str, *args: Any) -> RedisPipeline:
        """Queue a command onto the batch (fluent — chain calls, then :meth:`execute`)."""
        self._pipe.execute_command(name, *args)
        return self

    async def execute(self) -> list[Any]:
        """Flush the batch in one round trip; returns each command's result, in order."""
        return list(await self._pipe.execute())


class RedisConnection:
    """A thin, typed async wrapper over one ``redis.asyncio.Redis`` client."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._client: Any = None

    def _connect(self) -> Any:
        if self._client is None:
            try:
                import redis.asyncio as redis_asyncio
            except ImportError as exc:
                raise MissingExtraError("redis", "redis") from exc
            self._client = redis_asyncio.from_url(self._url)
        return self._client

    async def command(self, name: str, *args: Any) -> Any:
        """Run a single redis command by name, e.g.
        ``await redis.command("SET", "k", "v")``."""
        attrs = {"db.system": "redis", "db.operation": name}
        with span(f"redis {name}", kind="client", attributes=attrs):
            return await self._connect().execute_command(name, *args)

    @contextlib.asynccontextmanager
    async def pipeline(self, transaction: bool = False) -> AsyncGenerator[RedisPipeline]:
        """Batch commands into one round trip: ``async with conn.pipeline() as pipe: ...``."""
        client = self._connect()
        raw = client.pipeline(transaction=transaction)
        attrs = {"db.system": "redis", "db.operation": "pipeline"}
        with span("redis pipeline", kind="client", attributes=attrs):
            yield RedisPipeline(raw)

    async def publish(self, channel: str, message: Any) -> int:
        """Publish ``message`` on ``channel``; returns the number of subscribers that received it."""
        attrs = {"messaging.destination": channel, "messaging.system": "redis"}
        with span("redis publish", kind="producer", attributes=attrs):
            return int(await self._connect().publish(channel, message))

    async def subscribe(self, channel: str) -> AsyncIterator[str]:
        """Yield each message published on ``channel`` as ``str`` (cancel the consuming task, or
        break out of the loop, to unsubscribe and release the pubsub connection)."""
        pubsub = self._connect().pubsub()
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                data = message["data"]
                yield data.decode() if isinstance(data, bytes) else data
        finally:
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()

    async def eval(
        self, script: str, keys: list[str] | None = None, args: list[Any] | None = None
    ) -> Any:
        """Run a Lua script (``EVAL``); ``keys``/``args`` map to Redis's ``KEYS``/``ARGV``."""
        redis_keys = keys or []
        redis_args = args or []
        attrs = {"db.system": "redis", "db.operation": "eval"}
        with span("redis eval", kind="client", attributes=attrs):
            return await self._connect().eval(script, len(redis_keys), *redis_keys, *redis_args)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class RedisManager:
    """Resolves + caches named Redis connections."""

    def __init__(self, app: Any = None) -> None:
        self.app = app
        self._connections: dict[str, RedisConnection] = {}

    def _settings(self) -> RedisSettings:
        app = self.app
        if app is not None and hasattr(app, "config"):
            return RedisSettings.from_source(app.config("redis"))
        return RedisSettings()

    def _url_for(self, name: str) -> str:
        settings = self._settings()
        if name in settings.connections:
            return str(settings.connections[name].get("url", settings.url))
        if name == "default":
            return settings.url
        raise KeyError(f"No redis connection named {name!r}")

    def connection(self, name: str | None = None) -> RedisConnection:
        key = name or "default"
        if key not in self._connections:
            self._connections[key] = RedisConnection(self._url_for(key))
        return self._connections[key]

    async def close_all(self) -> None:
        for conn in self._connections.values():
            await conn.close()
        self._connections.clear()

    def __getattr__(self, item: str) -> Any:
        # Forward unknown attributes to the default connection (Redis.command(...) -> default).
        if item.startswith("_"):
            raise AttributeError(item)
        return getattr(self.connection(), item)


__all__ = ["RedisConnection", "RedisManager", "RedisPipeline", "RedisSettings"]
