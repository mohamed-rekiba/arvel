"""QueueServiceProvider — registers the queue subsystem."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from arvel.console._subsystem import CliSubsystem
from arvel.providers.service_provider import ServiceProvider

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from arvel.queue.failed_job_store import FailedJobStore


class QueueServiceProvider(ServiceProvider):
    """Registers QueueManager, Bus, FailedJobStore, and binds the Bus facade.

    ``app`` may be an ``Application`` or a bare ``Container`` (used in tests).
    Tagged ``CliSubsystem.QUEUE``; the closure pulls in ``DATABASE``
    automatically for DB-backed drivers.
    """

    subsystem: ClassVar[CliSubsystem | None] = CliSubsystem.QUEUE

    def register(self) -> None:
        from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

        from arvel.queue.bus import Bus
        from arvel.queue.config import QueueConfig
        from arvel.queue.failed_job_store import FailedJobStore
        from arvel.queue.manager import QueueManager

        config = QueueConfig()
        manager = QueueManager(
            config,
            database_session_factory=self._make_optional(async_sessionmaker[AsyncSession]),
            database_engine=self._make_optional(AsyncEngine),
        )
        bus = Bus(manager)

        self.container.instance(QueueConfig, config)
        self.container.instance(QueueManager, manager)
        self.container.instance(Bus, bus)
        self.container.singleton(FailedJobStore, self._failed_store_factory)

    def _make_optional(self, abstract: type[Any]) -> Any | None:
        try:
            return self.container.make(abstract)
        except Exception:
            return None

    async def boot(self) -> None:
        from arvel.facades.bus import Bus as BusFacade
        from arvel.queue import migrations as queue_migrations

        BusFacade.bind(self.container)

        stub_dir = Path(queue_migrations.__file__).parent
        self.publishes(
            {
                stub_dir / "create_jobs_table.py": "database/migrations",
                stub_dir / "create_failed_jobs_table.py": "database/migrations",
            },
            tag="arvel-queue",
            is_migrations=True,
        )

    async def shutdown(self) -> None:
        from arvel.queue.manager import QueueManager

        manager: QueueManager = self.container.make(QueueManager)
        await manager.close_all()

    def commands(self) -> list[Any]:
        from arvel.queue.commands.queue_failed import QueueFailedCommand
        from arvel.queue.commands.queue_flush import QueueFlushCommand
        from arvel.queue.commands.queue_forget import QueueForgetCommand
        from arvel.queue.commands.queue_retry import QueueRetryCommand
        from arvel.queue.commands.queue_size import QueueSizeCommand
        from arvel.queue.commands.queue_work import QueueWorkCommand
        from arvel.queue.failed_job_store import FailedJobStore
        from arvel.queue.manager import QueueManager

        manager: QueueManager = self.container.make(QueueManager)
        store: FailedJobStore = self.container.make(FailedJobStore)

        return [
            QueueWorkCommand(manager, failed_job_store=store),
            QueueFailedCommand(store),
            QueueRetryCommand(manager, store),
            QueueFlushCommand(store),
            QueueForgetCommand(store),
            QueueSizeCommand(manager),
        ]

    def _failed_store_factory(self) -> FailedJobStore:
        from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

        from arvel.queue.failed_job_store import FailedJobStore

        # Reuse the DatabaseServiceProvider's session-maker if available.
        try:
            factory: async_sessionmaker[AsyncSession] = self.container.make(
                async_sessionmaker[AsyncSession]
            )
            return FailedJobStore(factory)
        # Optional binding can be absent; fall through to engine + in-memory fallback chain.
        except Exception:  # nosec B110
            pass

        # Fall back to the raw engine if available.
        try:
            engine = self.container.make(AsyncEngine)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            return FailedJobStore(factory)
        # Optional SQLAlchemy binding can be absent; last-resort in-memory fallback below.
        except Exception:  # nosec B110
            pass

        # Last resort: in-memory SQLite (tests and minimal environments).
        from sqlalchemy.ext.asyncio import create_async_engine

        fallback = create_async_engine("sqlite+aiosqlite:///:memory:")
        factory = async_sessionmaker(fallback, expire_on_commit=False)
        store = FailedJobStore(factory)
        store.set_engine(fallback)
        return store


__all__ = ["QueueServiceProvider"]
