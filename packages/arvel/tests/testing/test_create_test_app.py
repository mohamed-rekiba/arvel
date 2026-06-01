"""Tests for create_test_app() async context manager.
Tests are written RED — arvel.testing.create_test_app does not exist yet.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from starlette.types import ASGIApp

#: importable, not from arvel root


def test_importable_from_arvel_testing() -> None:
    from arvel.testing import create_test_app

    assert callable(create_test_app)


def test_not_importable_from_arvel_root() -> None:
    """create_test_app must NOT be in arvel root namespace (production guard)."""
    import arvel

    assert not hasattr(arvel, "create_test_app"), (
        "create_test_app leaked into arvel root — production code guard violation"
    )


#: boots and shuts down


@pytest.mark.asyncio
async def test_create_test_app_boots_and_shuts_down() -> None:
    """create_test_app() must boot providers on entry and shut down on exit."""
    from arvel.testing import create_test_app

    boot_count = 0
    shutdown_count = 0

    class FakeApplication:
        async def boot(self) -> None:
            nonlocal boot_count
            boot_count += 1

        async def shutdown(self) -> None:
            nonlocal shutdown_count
            shutdown_count += 1

        def into_asgi(self) -> ASGIApp:
            from starlette.responses import Response
            from starlette.types import Receive, Scope, Send

            async def app(scope: Scope, receive: Receive, send: Send) -> None:
                await Response("ok")(scope, receive, send)

            return app

    app = FakeApplication()
    async with create_test_app(app) as client:
        response = await client.get("http://test/")
        assert response.status_code == 200

    assert boot_count == 1, "boot() must be called exactly once"
    assert shutdown_count == 1, "shutdown() must be called exactly once on exit"


#: no Any types


def test_no_any_in_asgi_types() -> None:
    """arvel.testing.app must use starlette.types.Scope/Receive/Send, not Any."""
    import inspect

    import arvel.testing.app as app_module

    source = inspect.getsource(app_module)
    # Must not import Any from typing for ASGI callable parameters
    # This is verified at the mypy level; here we just check source
    assert "scope: dict[str, Any]" not in source, (
        "ASGI scope parameter must use starlette.types.Scope, not dict[str, Any]"
    )


# default base_url


@pytest.mark.asyncio
async def test_default_base_url_is_http_test() -> None:
    from arvel.testing import create_test_app

    class MinimalApp:
        async def boot(self) -> None: ...
        async def shutdown(self) -> None: ...

        def into_asgi(self) -> ASGIApp:
            from starlette.responses import JSONResponse
            from starlette.types import Receive, Scope, Send

            async def app(scope: Scope, receive: Receive, send: Send) -> None:
                await JSONResponse({"host": "ok"})(scope, receive, send)

            return app

    async with create_test_app(MinimalApp()) as client:
        # AsyncClient.base_url should default to "http://test"
        assert "test" in str(client.base_url)
