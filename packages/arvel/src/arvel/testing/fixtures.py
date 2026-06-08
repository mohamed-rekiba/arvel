"""Pytest fixtures for Arvel apps — register via ``pytest_plugins = ["arvel.testing.fixtures"]``."""

from __future__ import annotations

import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from httpx2 import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from arvel.application import Application


@pytest_asyncio.fixture
async def arvel_app() -> AsyncIterator[Application]:
    """Boot a minimal Arvel app for the test."""
    from arvel.application import ApplicationBuilder
    from arvel.providers import ConfigServiceProvider, HttpServiceProvider

    base = Path(tempfile.mkdtemp(prefix="arvel-app-"))
    # HttpServiceProvider binds Router + HttpExceptionHandler so the client
    # fixture can call ``arvel_app.into_asgi()`` without manual setup.
    app = (
        ApplicationBuilder(base_path=base)
        .with_providers([ConfigServiceProvider, HttpServiceProvider])
        .create()
    )
    await app.boot()
    try:
        yield app
    finally:
        await app.shutdown()


@pytest_asyncio.fixture
async def arvel_client(arvel_app: Application) -> AsyncIterator[AsyncClient]:
    """An httpx AsyncClient bound to the test app's ASGI surface."""
    transport = ASGITransport(app=arvel_app.into_asgi())
    client = AsyncClient(transport=transport, base_url="http://testserver")
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
def arvel_database(arvel_app: Application) -> Application:
    """Placeholder DB fixture — apps with the DatabaseServiceProvider can override."""
    return arvel_app


__all__ = ["arvel_app", "arvel_client", "arvel_database"]
