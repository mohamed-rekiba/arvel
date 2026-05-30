"""Scheduler control signals via cache markers.

Mirrors the ``QueueRestartSignal`` pattern so any registered cache store
(Redis, database, array) acts as the coordination layer across processes.
All methods degrade gracefully when the cache facade is unbound.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arvel.cache.store import CacheStore

_INTERRUPT_KEY = "arvel:scheduler:interrupt"
_PAUSED_KEY = "arvel:scheduler:paused"


class SchedulerSignal:
    """Reads and writes scheduler control markers in the cache.

    ``send_interrupt()`` tells a running ``serve_forever()`` loop to exit
    at its next tick boundary. ``pause()``/``resume()`` tell it to skip
    ``run_due_tasks()`` without exiting.
    """

    def __init__(
        self,
        *,
        interrupt_key: str = _INTERRUPT_KEY,
        paused_key: str = _PAUSED_KEY,
    ) -> None:
        self._interrupt_key = interrupt_key
        self._paused_key = paused_key

    async def send_interrupt(self) -> None:
        """Write the interrupt marker. Expires in 120 s to avoid stale signals."""
        store = self._resolve_store()
        if store is not None:
            await store.put(self._interrupt_key, "1", ttl=120)

    async def check_and_clear_interrupt(self) -> bool:
        """Return True (and delete the marker) when an interrupt was signalled."""
        store = self._resolve_store()
        if store is None:
            return False
        raw = await store.get(self._interrupt_key)
        if raw is not None:
            await store.forget(self._interrupt_key)
            return True
        return False

    async def pause(self) -> None:
        """Write the pause marker (no TTL — stays until resume())."""
        store = self._resolve_store()
        if store is not None:
            await store.put(self._paused_key, "1")

    async def resume(self) -> None:
        """Delete the pause marker."""
        store = self._resolve_store()
        if store is not None:
            await store.forget(self._paused_key)

    async def is_paused(self) -> bool:
        """True when the pause marker is present in the cache."""
        store = self._resolve_store()
        if store is None:
            return False
        return await store.get(self._paused_key) is not None

    @staticmethod
    def _resolve_store() -> CacheStore | None:
        from arvel.cache.exceptions import FacadeNotBoundError
        from arvel.facades.cache import Cache

        try:
            return Cache.store(None)
        except FacadeNotBoundError:
            return None


__all__ = ["SchedulerSignal"]
