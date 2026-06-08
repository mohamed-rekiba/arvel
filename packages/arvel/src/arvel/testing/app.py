"""create_test_app — async context manager for in-process ASGI testing.

Usage::

 async with create_test_app(my_app) as client:
 response = await client.get("http://test/health")
 assert response.status_code == 200

The context manager:
1. Calls ``app.boot`` on entry.
2. Wraps the ASGI callable returned by ``app.into_asgi`` in an
 ``httpx.AsyncClient``.
3. Calls ``app.shutdown`` on exit, even if the body raises.

This replaces the kit's ``StarterApp``/``create_app`` pattern which used
``Any`` for the ASGI scope/receive/send types. Here we use the typed
``starlette.types.Scope``, ``Receive``, ``Send`` throughout so mypy --strict
passes with no suppression comments.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Protocol, runtime_checkable

import httpx2 as httpx
from starlette.types import ASGIApp


@runtime_checkable
class _BootableApp(Protocol):
    """Minimal protocol for an Arvel (or test-double) application."""

    async def boot(self) -> None: ...
    async def shutdown(self) -> None: ...
    def into_asgi(self) -> ASGIApp: ...


@asynccontextmanager
async def create_test_app(
    app: _BootableApp,
    *,
    base_url: str = "http://test",
) -> AsyncGenerator[httpx.AsyncClient]:
    """Boot ``app``, yield an ``AsyncClient``, then shut down on exit.

    ``app`` must implement the :class:`_BootableApp` protocol (all Arvel
    ``Application`` instances do).
    """
    await app.boot()
    asgi = app.into_asgi()
    transport = httpx.ASGITransport(app=asgi)
    async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
        try:
            yield client
        finally:
            await app.shutdown()


__all__ = ["create_test_app"]
