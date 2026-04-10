"""DatabaseServiceProvider — wires async engine + session factory into DI.

Each provider instance owns its own engine and session factory so that
multiple ``Application`` instances (common in tests) don't interfere
with each other through shared module-level globals.

Shutdown is scope-aware: the class-level resolvers on ``ArvelModel``
are only cleared if this provider instance was the last one to set
them.  This prevents a short-lived Application (e.g. in a test) from
wiping the resolver that a long-lived session-scoped Application
registered.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from arvel.data.config import DatabaseSettings
from arvel.foundation.container import Scope
from arvel.foundation.provider import ServiceProvider
from arvel.logging import Log

if TYPE_CHECKING:
    from arvel.foundation.application import Application
    from arvel.foundation.container import ContainerBuilder

_logger = Log.named("arvel.data.provider")


class DatabaseServiceProvider(ServiceProvider):
    """Registers the async database engine and session factory.

    Priority 5 — boots before infrastructure (10) so the database
    is available for health checks and other providers.

    Also sets the default session resolver on ``ArvelModel`` so that
    ``User.query()`` works without passing a session explicitly.
    """

    priority: int = 5

    _engine: AsyncEngine | None
    _session_factory: async_sessionmaker[AsyncSession] | None
    _own_session_resolver: Any
    _own_observer_resolver: Any

    def __init__(self) -> None:
        super().__init__()
        self._engine = None
        self._session_factory = None
        self._own_session_resolver = None
        self._own_observer_resolver = None

    def _make_engine(self) -> AsyncEngine:
        if self._engine is not None:
            return self._engine

        import logging

        settings = DatabaseSettings()
        kwargs: dict[str, Any] = {
            "echo": False,
            "pool_pre_ping": settings.pool_pre_ping,
            "pool_recycle": settings.pool_recycle,
        }
        if settings.driver != "sqlite":
            kwargs["pool_size"] = settings.pool_size
            kwargs["max_overflow"] = settings.pool_max_overflow
            kwargs["pool_timeout"] = settings.pool_timeout

        self._engine = create_async_engine(settings.url, **kwargs)

        if settings.echo:
            logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.DEBUG)

        _logger.info("database_engine_created", url=settings.url.split("@")[-1])
        return self._engine

    def _make_session_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._session_factory is not None:
            return self._session_factory

        settings = DatabaseSettings()
        engine = self._make_engine()
        self._session_factory = async_sessionmaker(
            engine,
            expire_on_commit=settings.expire_on_commit,
        )
        return self._session_factory

    def _make_session(self) -> AsyncSession:
        """Create a fresh (unmanaged) session for CRUD write operations."""
        factory = self._make_session_factory()
        return factory()

    async def register(self, container: ContainerBuilder) -> None:
        container.provide_factory(AsyncEngine, self._make_engine, scope=Scope.APP)
        container.provide_factory(
            async_sessionmaker,
            self._make_session_factory,
            scope=Scope.APP,  # type: ignore[type-abstract]
        )
        container.provide_factory(AsyncSession, self._make_session, scope=Scope.REQUEST)

    async def boot(self, app: Application) -> None:
        from arvel.data.model import ArvelModel
        from arvel.data.observer import ObserverRegistry

        session_resolver = self._make_session
        if ArvelModel._session_resolver is None:
            ArvelModel.set_session_resolver(session_resolver)
            ArvelModel.set_session_factory(session_resolver)
            self._own_session_resolver = session_resolver
        else:
            self._own_session_resolver = None

        if ArvelModel._observer_registry_resolver is None:
            _registry = ObserverRegistry()
            observer_resolver = lambda: _registry  # noqa: E731
            ArvelModel.set_observer_registry(observer_resolver)
            self._own_observer_resolver = observer_resolver
        else:
            self._own_observer_resolver = None

        _logger.info("database_session_and_observer_resolver_set")

    async def shutdown(self, app: Application) -> None:
        from arvel.data.model import ArvelModel

        if (
            self._own_session_resolver is not None
            and ArvelModel._session_resolver is self._own_session_resolver
        ):
            ArvelModel.clear_session_resolver()
        if (
            self._own_observer_resolver is not None
            and ArvelModel._observer_registry_resolver is self._own_observer_resolver
        ):
            ArvelModel.clear_observer_registry()

        if self._engine is not None:
            await self._engine.dispose()
            _logger.info("database_engine_disposed")
            self._engine = None
        self._session_factory = None
