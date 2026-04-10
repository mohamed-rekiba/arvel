"""Tests for DatabaseServiceProvider — engine, session factory, and session DI wiring."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from arvel.data.provider import DatabaseServiceProvider
from arvel.foundation.container import ContainerBuilder


@pytest.fixture(scope="module", params=["asyncio"], autouse=True)
def anyio_backend(request: pytest.FixtureRequest) -> str:
    return request.param


class TestMakeEngine:
    """Engine factory creates a valid AsyncEngine from DatabaseSettings."""

    def test_make_engine_returns_async_engine(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DB_DRIVER", "sqlite")
        monkeypatch.setenv("DB_DATABASE", ":memory:")
        provider = DatabaseServiceProvider()
        engine = provider._make_engine()
        assert isinstance(engine, AsyncEngine)

    def test_make_engine_is_cached(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DB_DRIVER", "sqlite")
        monkeypatch.setenv("DB_DATABASE", ":memory:")
        provider = DatabaseServiceProvider()
        first = provider._make_engine()
        second = provider._make_engine()
        assert first is second


class TestMakeSession:
    """Session factory produces fresh AsyncSession instances."""

    def test_make_session_returns_async_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DB_DRIVER", "sqlite")
        monkeypatch.setenv("DB_DATABASE", ":memory:")
        provider = DatabaseServiceProvider()
        session = provider._make_session()
        assert isinstance(session, AsyncSession)

    def test_make_session_returns_new_instance_each_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DB_DRIVER", "sqlite")
        monkeypatch.setenv("DB_DATABASE", ":memory:")
        provider = DatabaseServiceProvider()
        s1 = provider._make_session()
        s2 = provider._make_session()
        assert s1 is not s2


class TestDatabaseServiceProviderRegister:
    """Provider registers engine, session factory, and session in the container."""

    @pytest.mark.anyio
    async def test_register_binds_engine(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DB_DRIVER", "sqlite")
        monkeypatch.setenv("DB_DATABASE", ":memory:")
        builder = ContainerBuilder()
        provider = DatabaseServiceProvider()
        await provider.register(builder)
        container = builder.build()
        engine = await container.resolve(AsyncEngine)
        assert isinstance(engine, AsyncEngine)

    @pytest.mark.anyio
    async def test_register_binds_session_factory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DB_DRIVER", "sqlite")
        monkeypatch.setenv("DB_DATABASE", ":memory:")
        builder = ContainerBuilder()
        provider = DatabaseServiceProvider()
        await provider.register(builder)
        container = builder.build()
        factory = await container.resolve(async_sessionmaker)
        assert isinstance(factory, async_sessionmaker)

    @pytest.mark.anyio
    async def test_register_binds_async_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DB_DRIVER", "sqlite")
        monkeypatch.setenv("DB_DATABASE", ":memory:")
        builder = ContainerBuilder()
        provider = DatabaseServiceProvider()
        await provider.register(builder)
        container = builder.build()
        session = await container.resolve(AsyncSession)
        assert isinstance(session, AsyncSession)


class TestDatabaseServiceProviderBoot:
    """Boot sets the session resolver on ArvelModel."""

    @pytest.mark.anyio
    async def test_boot_sets_session_resolver(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DB_DRIVER", "sqlite")
        monkeypatch.setenv("DB_DATABASE", ":memory:")

        from unittest.mock import MagicMock

        from arvel.data.model import ArvelModel

        ArvelModel.clear_session_resolver()
        assert ArvelModel._session_resolver is None

        mock_app = MagicMock()
        provider = DatabaseServiceProvider()
        await provider.boot(mock_app)

        assert ArvelModel._session_resolver is not None
        session = ArvelModel._session_resolver()
        from sqlalchemy.ext.asyncio import AsyncSession

        assert isinstance(session, AsyncSession)
        ArvelModel.clear_session_resolver()


class TestDatabaseServiceProviderShutdown:
    """Shutdown disposes the engine and clears instance state."""

    @pytest.mark.anyio
    async def test_shutdown_disposes_engine(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DB_DRIVER", "sqlite")
        monkeypatch.setenv("DB_DATABASE", ":memory:")

        from unittest.mock import MagicMock

        from arvel.data.model import ArvelModel

        ArvelModel.clear_session_resolver()
        ArvelModel.clear_observer_registry()

        mock_app = MagicMock()
        provider = DatabaseServiceProvider()
        await provider.boot(mock_app)

        # boot() lazily stores a session resolver — materialize the engine
        provider._make_session()
        assert provider._engine is not None

        await provider.shutdown(mock_app)

        assert provider._engine is None
        assert provider._session_factory is None

    @pytest.mark.anyio
    async def test_shutdown_noop_when_no_engine(self) -> None:
        from unittest.mock import MagicMock

        mock_app = MagicMock()
        provider = DatabaseServiceProvider()
        await provider.shutdown(mock_app)
        assert provider._engine is None
