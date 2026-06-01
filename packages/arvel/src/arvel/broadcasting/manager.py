"""BroadcastManager — driver factory."""

from __future__ import annotations

import importlib
from typing import cast

from arvel.broadcasting.config import BroadcastConfig, BroadcastDriver
from arvel.broadcasting.exceptions import BroadcastDriverError
from arvel.broadcasting.protocol import Broadcaster


class BroadcastManager:
    """Holds a per-name singleton dict of resolved drivers.

    Resolution is lazy; ``driver()`` builds the driver on first request and
    re-uses it on subsequent calls.
    """

    def __init__(self, config: BroadcastConfig) -> None:
        self._config: BroadcastConfig = config
        self._drivers: dict[BroadcastDriver, Broadcaster] = {}
        self._channels: dict[str, type] = {}

    @property
    def config(self) -> BroadcastConfig:
        return self._config

    def register_channel(self, name: str, handler: type) -> None:
        """Register a channel handler under ``name``. Last registration wins."""
        self._channels[name] = handler

    def channels(self) -> dict[str, type]:
        """Return a snapshot of the registered channels."""
        return dict(self._channels)

    def driver(self, name: str | None = None) -> Broadcaster:
        try:
            key = self._config.default if name is None else BroadcastDriver(name)
        except ValueError as exc:
            raise BroadcastDriverError(f"Unknown broadcast driver: {name!r}") from exc
        if key not in self._drivers:
            self._drivers[key] = self._make(key)
        return self._drivers[key]

    def _make(self, key: BroadcastDriver) -> Broadcaster:
        if key is BroadcastDriver.LOG:
            from arvel.broadcasting.drivers.log import LogBroadcaster

            return LogBroadcaster()
        if key is BroadcastDriver.NULL:
            from arvel.broadcasting.drivers.null import NullBroadcaster

            return NullBroadcaster()
        if key is BroadcastDriver.REDIS_PUBSUB:
            return self._make_redis()
        if key is BroadcastDriver.PUSHER:
            return self._make_pusher()
        raise BroadcastDriverError(f"Unsupported broadcast driver: {key!r}")

    def _make_redis(self) -> Broadcaster:
        try:
            aioredis = importlib.import_module("redis.asyncio")
        except ImportError as exc:
            raise BroadcastDriverError(
                "Redis broadcaster requires arvel[redis]. Install with: pip install 'arvel[redis]'",
            ) from exc
        from arvel.broadcasting.drivers.redis import AsyncRedis, RedisBroadcaster

        client = cast("AsyncRedis", aioredis.Redis())
        return RedisBroadcaster(redis=client)

    def _make_pusher(self) -> Broadcaster:
        # PusherBroadcaster only needs httpx, which we already ship.

        # We need a ReverbConfig (or PusherConfig) for credentials. For now the
        # simplest contract is: callers wire PusherBroadcaster directly via the
        # provider. Without explicit credentials in BroadcastConfig (none yet),
        # we can't safely instantiate — raise so misuse is visible.
        raise BroadcastDriverError(
            "PusherBroadcaster cannot be auto-built from BroadcastConfig — wire it "
            "explicitly in your service provider with app_id/key/secret.",
        )


__all__ = ["BroadcastManager"]
