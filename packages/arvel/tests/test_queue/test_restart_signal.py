"""Queue restart signal coverage."""

from __future__ import annotations

from arvel.cache import CacheManager
from arvel.config.cache_config import CacheConfig, CacheDriver
from arvel.facades.cache import Cache
from arvel.queue.restart import QueueRestartSignal


async def test_queue_restart_signal_without_cache_returns_none() -> None:
    previous = Cache.manager
    Cache.manager = None
    try:
        signal = QueueRestartSignal()
        assert await signal.last_restart() is None
    finally:
        Cache.manager = previous


async def test_queue_restart_signal_roundtrip() -> None:
    previous = Cache.manager
    Cache.manager = CacheManager(CacheConfig(connection=CacheDriver.ARRAY))
    try:
        signal = QueueRestartSignal(cache_key="queue:restart:test")
        marker = await signal.signal_restart()

        assert signal.cache_key == "queue:restart:test"
        assert await signal.last_restart() == marker
    finally:
        Cache.manager = previous


async def test_queue_restart_signal_ignores_invalid_marker() -> None:
    previous = Cache.manager
    Cache.manager = CacheManager(CacheConfig(connection=CacheDriver.ARRAY))
    try:
        signal = QueueRestartSignal(cache_key="queue:restart:bad")
        await Cache.store().put(signal.cache_key, "not-a-date")

        assert await signal.last_restart() is None
    finally:
        Cache.manager = previous
