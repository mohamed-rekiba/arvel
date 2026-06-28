"""arvel.client — the ``Http`` client over **httpx** (core; DR-0002).

A fluent, async HTTP client (Laravel ``Http`` facade parity): ``with_headers`` /
``with_token`` / ``base_url`` / ``timeout`` then ``get``/``post``/…, returning a
real ``httpx.Response``. Separate from the ``[http]`` web module. httpx is core.
"""

from __future__ import annotations

from typing import Any

import httpx


class PendingRequest:
    """A configurable, sendable HTTP request."""

    def __init__(self, transport: Any = None) -> None:
        self._headers: dict[str, str] = {}
        self._base_url: str = ""
        self._timeout: float = 30.0
        self._transport = transport

    def with_headers(self, headers: dict[str, str]) -> PendingRequest:
        self._headers.update(headers)
        return self

    def with_token(self, token: str, scheme: str = "Bearer") -> PendingRequest:
        self._headers["Authorization"] = f"{scheme} {token}"
        return self

    def base_url(self, url: str) -> PendingRequest:
        self._base_url = url
        return self

    def timeout(self, seconds: float) -> PendingRequest:
        self._timeout = seconds
        return self

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        async with httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=self._timeout,
            transport=self._transport,
        ) as client:
            return await client.request(method, url, **kwargs)

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("DELETE", url, **kwargs)


class Client:
    """The ``Http`` factory (bound as ``http``). Each call starts a fresh request."""

    def __init__(self, transport: Any = None) -> None:
        self._transport = transport

    def _pending(self) -> PendingRequest:
        return PendingRequest(transport=self._transport)

    def with_headers(self, headers: dict[str, str]) -> PendingRequest:
        return self._pending().with_headers(headers)

    def with_token(self, token: str, scheme: str = "Bearer") -> PendingRequest:
        return self._pending().with_token(token, scheme)

    def base_url(self, url: str) -> PendingRequest:
        return self._pending().base_url(url)

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._pending().get(url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._pending().post(url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._pending().put(url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._pending().patch(url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._pending().delete(url, **kwargs)


__all__ = ["Client", "PendingRequest"]
