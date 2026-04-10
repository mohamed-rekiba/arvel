"""Async HTTP test client wrapping httpx.AsyncClient with ASGI transport."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from arvel.testing.assertions import TestResponse

if TYPE_CHECKING:
    from fastapi import FastAPI
    from httpx._types import (
        AuthTypes,
        CookieTypes,
        HeaderTypes,
        QueryParamTypes,
        RequestContent,
        RequestData,
        RequestExtensions,
        RequestFiles,
        TimeoutTypes,
    )


class TestClient:
    __test__ = False

    """Test client for Arvel apps.

    Wraps ``httpx.AsyncClient`` with ``ASGITransport`` so requests go through
    the full middleware pipeline. Supports ``acting_as()`` for injecting auth
    context into subsequent requests.

    Usage::

        async with TestClient(app) as client:
            client.acting_as(user_id=42, headers={"Authorization": "Bearer tok"})
            resp = await client.get("/me")
    """

    def __init__(self, app: FastAPI, base_url: str = "http://testserver") -> None:
        self._transport = httpx.ASGITransport(app=app)
        self._base_url = base_url
        self._extra_headers: dict[str, str] = {}
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> TestClient:
        self._client = httpx.AsyncClient(
            transport=self._transport,
            base_url=self._base_url,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def acting_as(
        self,
        *,
        user_id: int | str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Inject auth headers for subsequent requests.

        Any headers passed here persist for the lifetime of this client session.
        """
        if headers:
            self._extra_headers.update(headers)
        if user_id is not None and "X-User-ID" not in self._extra_headers:
            self._extra_headers["X-User-ID"] = str(user_id)

    def _merge_headers(self, headers: HeaderTypes | None) -> dict[str, str]:
        merged: dict[str, str] = dict(self._extra_headers)
        if headers is not None:
            for key, value in dict(headers).items():
                merged[str(key)] = str(value)
        return merged

    def _ensure_open(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Use `async with TestClient(app) as client:`")
        return self._client

    async def get(
        self,
        url: str,
        *,
        params: QueryParamTypes | None = None,
        headers: HeaderTypes | None = None,
        cookies: CookieTypes | None = None,
        auth: AuthTypes | None = None,
        follow_redirects: bool = True,
        timeout: TimeoutTypes | None = None,
        extensions: RequestExtensions | None = None,
    ) -> TestResponse:
        kw: dict[str, Any] = {
            "params": params,
            "headers": self._merge_headers(headers),
            "cookies": cookies,
            "follow_redirects": follow_redirects,
            "extensions": extensions,
        }
        if auth is not None:
            kw["auth"] = auth
        if timeout is not None:
            kw["timeout"] = timeout
        return TestResponse(await self._ensure_open().get(url, **kw))

    async def post(
        self,
        url: str,
        *,
        content: RequestContent | None = None,
        data: RequestData | None = None,
        files: RequestFiles | None = None,
        json: Any | None = None,
        params: QueryParamTypes | None = None,
        headers: HeaderTypes | None = None,
        cookies: CookieTypes | None = None,
        auth: AuthTypes | None = None,
        follow_redirects: bool = True,
        timeout: TimeoutTypes | None = None,
        extensions: RequestExtensions | None = None,
    ) -> TestResponse:
        kw: dict[str, Any] = {
            "content": content,
            "data": data,
            "files": files,
            "json": json,
            "params": params,
            "headers": self._merge_headers(headers),
            "cookies": cookies,
            "follow_redirects": follow_redirects,
            "extensions": extensions,
        }
        if auth is not None:
            kw["auth"] = auth
        if timeout is not None:
            kw["timeout"] = timeout
        return TestResponse(await self._ensure_open().post(url, **kw))

    async def put(
        self,
        url: str,
        *,
        content: RequestContent | None = None,
        data: RequestData | None = None,
        files: RequestFiles | None = None,
        json: Any | None = None,
        params: QueryParamTypes | None = None,
        headers: HeaderTypes | None = None,
        cookies: CookieTypes | None = None,
        auth: AuthTypes | None = None,
        follow_redirects: bool = True,
        timeout: TimeoutTypes | None = None,
        extensions: RequestExtensions | None = None,
    ) -> TestResponse:
        kw: dict[str, Any] = {
            "content": content,
            "data": data,
            "files": files,
            "json": json,
            "params": params,
            "headers": self._merge_headers(headers),
            "cookies": cookies,
            "follow_redirects": follow_redirects,
            "extensions": extensions,
        }
        if auth is not None:
            kw["auth"] = auth
        if timeout is not None:
            kw["timeout"] = timeout
        return TestResponse(await self._ensure_open().put(url, **kw))

    async def patch(
        self,
        url: str,
        *,
        content: RequestContent | None = None,
        data: RequestData | None = None,
        files: RequestFiles | None = None,
        json: Any | None = None,
        params: QueryParamTypes | None = None,
        headers: HeaderTypes | None = None,
        cookies: CookieTypes | None = None,
        auth: AuthTypes | None = None,
        follow_redirects: bool = True,
        timeout: TimeoutTypes | None = None,
        extensions: RequestExtensions | None = None,
    ) -> TestResponse:
        kw: dict[str, Any] = {
            "content": content,
            "data": data,
            "files": files,
            "json": json,
            "params": params,
            "headers": self._merge_headers(headers),
            "cookies": cookies,
            "follow_redirects": follow_redirects,
            "extensions": extensions,
        }
        if auth is not None:
            kw["auth"] = auth
        if timeout is not None:
            kw["timeout"] = timeout
        return TestResponse(await self._ensure_open().patch(url, **kw))

    async def delete(
        self,
        url: str,
        *,
        params: QueryParamTypes | None = None,
        headers: HeaderTypes | None = None,
        cookies: CookieTypes | None = None,
        auth: AuthTypes | None = None,
        follow_redirects: bool = True,
        timeout: TimeoutTypes | None = None,
        extensions: RequestExtensions | None = None,
    ) -> TestResponse:
        kw: dict[str, Any] = {
            "params": params,
            "headers": self._merge_headers(headers),
            "cookies": cookies,
            "follow_redirects": follow_redirects,
            "extensions": extensions,
        }
        if auth is not None:
            kw["auth"] = auth
        if timeout is not None:
            kw["timeout"] = timeout
        return TestResponse(await self._ensure_open().delete(url, **kw))
