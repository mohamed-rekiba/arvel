"""QueueResource — the queue backing store as a health check (DR-0039).

Registered by ``QueueServiceProvider``. This is **check-only** (no connect/disconnect): the taskiq
broker's connection is owned by the *worker* process, not the web process. From the web process we
only want to know the queue's backing store is reachable, so ``check`` pings it: ``memory`` is
in-process (always OK), ``redis`` gets a ``PING``, ``amqp`` a short-lived connect probe.
"""

from __future__ import annotations

from typing import Any

from arvel.contracts import HealthResult, HealthStatus


class QueueResource:
    """Reachability of the queue's backing store. Non-critical by default: a broker outage degrades
    (jobs can buffer / retry) rather than aborting boot."""

    name = "queue:default"

    def __init__(self, driver: str, url: str, *, critical: bool = False) -> None:
        self._driver = driver
        self._url = url
        self.critical = critical

    async def check(self) -> HealthResult:
        if self._driver == "memory":
            return HealthResult(HealthStatus.OK, detail="in-memory")
        if self._driver == "redis":
            import redis.asyncio as redis_asyncio

            client: Any = redis_asyncio.from_url(
                self._url
            )  # redis stubs leave ping partially typed
            try:
                await client.ping()
            finally:
                await client.aclose()
            return HealthResult(HealthStatus.OK, detail="PING")
        # amqp — a short-lived connect proves the broker is reachable (the manager bounds it by timeout)
        import aio_pika

        connection = await aio_pika.connect(self._url)
        await connection.close()
        return HealthResult(HealthStatus.OK, detail="AMQP connect")
