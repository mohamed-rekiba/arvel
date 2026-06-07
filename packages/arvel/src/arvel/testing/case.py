"""ArvelTestCase — pytest-friendly base class for Arvel app tests."""

from __future__ import annotations

import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from arvel.testing.response import TestResponse

if TYPE_CHECKING:
    from arvel.application import Application
    from arvel.providers.service_provider import ServiceProvider


class ArvelTestCase:
    """Laravel-style base class — pytest collects coroutine methods natively
    when used with ``pytest-asyncio`` in ``mode=auto``.

    Usage::

        class TestPosts(ArvelTestCase):
            async def test_list(self) -> None:
                response = await self.client.get("/posts")
                response.assert_ok()

    Subclasses can override ``providers`` and ``base_path`` to customize boot.
    The default produces a minimal app with only the bare ConfigServiceProvider.
    """

    providers: tuple[type[ServiceProvider], ...] = ()
    base_path: Path | None = None

    app: Application
    client: httpx.AsyncClient

    async def asyncSetUp(self) -> None:
        from arvel.application import ApplicationBuilder
        from arvel.providers import ConfigServiceProvider, HttpServiceProvider

        base = self.base_path or Path(tempfile.mkdtemp(prefix="arvel-test-"))
        # HttpServiceProvider binds Router + HttpExceptionHandler, both of which
        # Application.into_asgi() needs to construct the FastAPI surface.
        provider_list: list[type[ServiceProvider]] = [
            ConfigServiceProvider,
            HttpServiceProvider,
            *self.providers,
        ]
        self.app = ApplicationBuilder(base_path=base).with_providers(provider_list).create()
        await self.app.boot()

        transport = httpx.ASGITransport(app=self.app.into_asgi())
        self.client = httpx.AsyncClient(transport=transport, base_url="http://testserver")

    async def asyncTearDown(self) -> None:
        if hasattr(self, "client"):
            await self.client.aclose()
        if hasattr(self, "app"):
            await self.app.shutdown()

    async def acting_as(self, user: object, guard: str = "web") -> None:
        """Authenticate the next request as ``user`` (test-only)."""
        env = getattr(self.app, "env", "testing")
        if env != "testing":
            raise RuntimeError("acting_as is test-only; refusing to run when env != 'testing'")
        user_id = getattr(user, "id", "anon")
        self.client.headers["Authorization"] = f"TestUser {user_id}"

    async def get_json(
        self,
        uri: str,
        *,
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> TestResponse:
        """GET ``uri`` with ``Accept: application/json`` and a wrapped response."""
        merged = {"Accept": "application/json", **(headers or {})}
        response = await self.client.get(uri, headers=merged, **kwargs)
        return TestResponse(response)

    async def post_json(
        self,
        uri: str,
        data: object = None,
        *,
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> TestResponse:
        """POST ``data`` as JSON with the right headers; returns a TestResponse."""
        merged = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            **(headers or {}),
        }
        response = await self.client.post(uri, json=data, headers=merged, **kwargs)
        return TestResponse(response)

    async def put_json(
        self,
        uri: str,
        data: object = None,
        *,
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> TestResponse:
        merged = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            **(headers or {}),
        }
        response = await self.client.put(uri, json=data, headers=merged, **kwargs)
        return TestResponse(response)

    async def patch_json(
        self,
        uri: str,
        data: object = None,
        *,
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> TestResponse:
        merged = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            **(headers or {}),
        }
        response = await self.client.patch(uri, json=data, headers=merged, **kwargs)
        return TestResponse(response)

    async def delete_json(
        self,
        uri: str,
        *,
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> TestResponse:
        merged = {"Accept": "application/json", **(headers or {})}
        response = await self.client.delete(uri, headers=merged, **kwargs)
        return TestResponse(response)


__all__ = ["ArvelTestCase"]
