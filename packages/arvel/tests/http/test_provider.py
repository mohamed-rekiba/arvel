"""HttpServiceProvider + into_asgi + serve."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import httpx
import pytest


@pytest.mark.asyncio
async def test_http_service_provider_binds_router(tmp_path: Path) -> None:
    from arvel import Application
    from arvel.providers import HttpServiceProvider
    from arvel.routing import Router

    Router.reset_singleton()
    app = (
        Application.configure(tmp_path)
        .with_environment("local")
        .with_providers([HttpServiceProvider])
        .create()
    )
    await app.boot()
    router = app.container.make(Router)
    assert isinstance(router, Router)


@pytest.mark.asyncio
async def test_http_service_provider_binds_handler(tmp_path: Path) -> None:
    from arvel import Application
    from arvel.http.exceptions import HttpExceptionHandler
    from arvel.providers import HttpServiceProvider
    from arvel.routing import Router

    Router.reset_singleton()
    app = (
        Application.configure(tmp_path)
        .with_environment("local")
        .with_providers([HttpServiceProvider])
        .create()
    )
    await app.boot()
    handler = app.container.make(HttpExceptionHandler)
    assert isinstance(handler, HttpExceptionHandler)


@pytest.mark.asyncio
async def test_http_service_provider_binds_default_ratelimit_store(tmp_path: Path) -> None:
    from arvel import Application
    from arvel.http.ratelimit import InMemoryStore, RateLimiterStore
    from arvel.providers import HttpServiceProvider
    from arvel.routing import Router

    Router.reset_singleton()
    app = (
        Application.configure(tmp_path)
        .with_environment("local")
        .with_providers([HttpServiceProvider])
        .create()
    )
    await app.boot()
    store = app.container.make(RateLimiterStore)  # type: ignore[type-abstract]
    assert isinstance(store, InMemoryStore)


@pytest.mark.asyncio
async def test_into_asgi_returns_wired_app_when_pre_booted(tmp_path: Path) -> None:
    from arvel import Application, ASGIApp
    from arvel.providers import HttpServiceProvider
    from arvel.routing import Route, Router
    from starlette.testclient import TestClient

    Router.reset_singleton()

    @Route.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    del health  # registered via @Route.get; drop local binding
    app = (
        Application.configure(tmp_path)
        .with_environment("local")
        .with_providers([HttpServiceProvider])
        .create()
    )
    await app.boot()
    fa = app.into_asgi()
    assert isinstance(fa, ASGIApp)
    assert cast("httpx.Client", TestClient(fa)).get("/healthz").json() == {"status": "ok"}


def test_into_asgi_default_lifespan_boots_and_shuts_down(tmp_path: Path) -> None:
    from arvel import Application, ASGIApp
    from arvel.providers import HttpServiceProvider
    from arvel.routing import Route, Router
    from starlette.testclient import TestClient

    Router.reset_singleton()

    @Route.get("/factory-boot")
    async def echo() -> dict[str, bool]:
        return {"ok": True}

    del echo  # registered via @Route.get; drop local binding
    app = (
        Application.configure(tmp_path)
        .with_environment("local")
        .with_providers([HttpServiceProvider])
        .create()
    )
    fa = app.into_asgi()
    assert isinstance(fa, ASGIApp)
    # The factory does not boot eagerly -- boot is wired into the lifespan.
    booted_at_factory_time = app._booted  # pyright: ignore[reportPrivateUsage]
    assert booted_at_factory_time is False

    with cast("httpx.Client", TestClient(fa)) as client:
        # Entering the TestClient context drives lifespan startup, which the
        # default lifespan uses to await self.boot().
        assert app._booted is True  # pyright: ignore[reportPrivateUsage]
        assert client.get("/factory-boot").json() == {"ok": True}

    # Exiting the context drives lifespan shutdown -> await self.shutdown().
    assert app._booted is False  # pyright: ignore[reportPrivateUsage]


def test_into_asgi_skips_double_boot_when_pre_booted(tmp_path: Path) -> None:
    import asyncio

    from arvel import Application
    from arvel.providers import HttpServiceProvider
    from arvel.routing import Router
    from starlette.testclient import TestClient

    Router.reset_singleton()
    app = (
        Application.configure(tmp_path)
        .with_environment("local")
        .with_providers([HttpServiceProvider])
        .create()
    )
    asyncio.run(app.boot())
    fa = app.into_asgi()
    # If the lifespan tried to re-boot a booted app, this would raise.
    with cast("httpx.Client", TestClient(fa)) as client:
        assert client.get("/__nonexistent__").status_code == 404
    assert app._booted is False  # pyright: ignore[reportPrivateUsage]
