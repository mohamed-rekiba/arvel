"""QueueManager — driver factory for the queue subsystem."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.queue.config import QueueConfig, QueueDriver
from arvel.queue.connection import QueueConnection
from arvel.queue.job import Job

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


class QueueManager:
    """Holds resolved driver instances and delegates operations to the active driver."""

    def __init__(
        self,
        config: QueueConfig,
        *,
        database_session_factory: async_sessionmaker[AsyncSession] | None = None,
        database_engine: AsyncEngine | None = None,
    ) -> None:
        self._config = config
        self._connections: dict[QueueDriver, QueueConnection] = {}
        self._database_session_factory = database_session_factory
        self._database_engine = database_engine

    def connection(self, name: QueueDriver | str | None = None) -> QueueConnection:
        """Return the named (or default) queue connection."""
        driver = self._config.connection if name is None else QueueDriver(name)
        if driver not in self._connections:
            self._connections[driver] = self._make_connection(driver)
        return self._connections[driver]

    def default_driver(self) -> QueueDriver:
        """Driver used when no name is passed to ``connection()``."""
        return self._config.connection

    def swap_connection(
        self,
        connection: QueueConnection,
        name: QueueDriver | str | None = None,
    ) -> QueueConnection | None:
        """Replace the cached connection for ``name`` (default driver if None).

        Returns the previous connection (or None if there was none). Test-only
        — used by ``Bus.fake()`` to install a recorder.
        """
        driver = self._config.connection if name is None else QueueDriver(name)
        previous = self._connections.get(driver)
        self._connections[driver] = connection
        return previous

    def restore_connection(
        self,
        previous: QueueConnection | None,
        name: QueueDriver | str | None = None,
    ) -> None:
        """Undo a ``swap_connection`` call, restoring the previous connection."""
        driver = self._config.connection if name is None else QueueDriver(name)
        if previous is None:
            self._connections.pop(driver, None)
        else:
            self._connections[driver] = previous

    def _make_connection(self, driver: QueueDriver) -> QueueConnection:
        if driver == QueueDriver.SYNC:
            from arvel.queue.drivers.sync import SyncConnection

            return SyncConnection()
        if driver == QueueDriver.DATABASE:
            from arvel.queue.drivers.database import DatabaseConnection

            return DatabaseConnection(
                self._config.database,
                session_factory=self._database_session_factory,
                engine=self._database_engine,
            )
        if driver == QueueDriver.REDIS:
            from arvel.queue.drivers.redis import RedisConnection

            return RedisConnection(self._config.redis)
        if driver == QueueDriver.TASKIQ:
            from arvel.queue.drivers.taskiq import TaskiqConnection

            return TaskiqConnection(self._config.taskiq)
        raise ValueError(f"Unknown queue driver: {driver!r}")

    async def push(self, job: Job, queue: str | None = None) -> None:
        target_queue = queue or job.queue
        conn = self.connection()
        await conn.push(job.to_envelope(), queue=target_queue)

    async def close_all(self) -> None:
        for conn in self._connections.values():
            await conn.close()
        self._connections.clear()


__all__ = ["QueueManager"]
