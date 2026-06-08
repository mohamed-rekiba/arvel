"""Meilisearch engine — talks to the REST API over httpx.

We use raw REST instead of the official SDK to keep the dependency footprint
small and the surface fully typed/mockable. Only the endpoints we need are
wired up. The master key is read from config (env), never hardcoded.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, cast

import httpx2 as httpx

from arvel_search.dtos import SearchResult
from arvel_search.engine import Engine
from arvel_search.exceptions import SearchError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Mapping, Sequence

    from arvel_search.dtos import SearchQuery


class MeilisearchEngine(Engine):
    """Index and query documents through a Meilisearch server."""

    def __init__(
        self,
        host: str,
        api_key: str = "",
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._host = host.rstrip("/")
        self._api_key = api_key
        self._http_client = http_client

    async def upsert_documents(
        self, index: str, documents: Sequence[Mapping[str, Any]], *, key: str
    ) -> None:
        if not documents:
            return
        async with self._client() as client:
            await self._request(
                client,
                "POST",
                f"/indexes/{index}/documents",
                params={"primaryKey": key},
                json=[dict(doc) for doc in documents],
            )

    async def remove_documents(self, index: str, keys: Sequence[str]) -> None:
        if not keys:
            return
        async with self._client() as client:
            await self._request(
                client,
                "POST",
                f"/indexes/{index}/documents/delete-batch",
                json=list(keys),
            )

    async def search(self, query: SearchQuery) -> SearchResult:
        body: dict[str, Any] = {"q": query.query, "offset": query.offset}
        if query.limit is not None:
            body["limit"] = query.limit
        if query.filters:
            body["filter"] = [f'{name} = "{value}"' for name, value in query.filters.items()]

        path = f"/indexes/{query.index}/search"
        async with self._client() as client:
            payload = await self._request(client, "POST", path, json=body)

        hits = cast("list[dict[str, Any]]", payload.get("hits", []))
        ids = [str(hit[query.key_name]) for hit in hits if query.key_name in hit]
        total = int(payload.get("estimatedTotalHits", len(ids)))
        return SearchResult(ids=ids, total=total, raw=payload)

    async def flush(self, index: str) -> None:
        async with self._client() as client:
            await self._request(client, "DELETE", f"/indexes/{index}/documents")

    async def delete_index(self, index: str) -> None:
        async with self._client() as client:
            await self._request(client, "DELETE", f"/indexes/{index}")

    @asynccontextmanager
    async def _client(self) -> AsyncGenerator[httpx.AsyncClient]:
        # An injected client is caller-owned — don't close it here.
        if self._http_client is not None:
            yield self._http_client
            return
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        async with httpx.AsyncClient(base_url=self._host, headers=headers, timeout=10.0) as client:
            yield client

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> dict[str, Any]:
        try:
            response = await client.request(method, path, params=params, json=json)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"Meilisearch request to {path} failed: {exc}"
            raise SearchError(msg) from exc
        if not response.content:
            return {}
        return cast("dict[str, Any]", response.json())


__all__ = ["MeilisearchEngine"]
