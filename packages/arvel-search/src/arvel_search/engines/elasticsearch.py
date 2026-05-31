"""Elasticsearch engine — bulk index + ``_search`` over httpx REST.

Like the Meilisearch driver, this hits the HTTP API directly rather than
pulling in the official client, keeping deps light and the code mockable.
The Elasticsearch ``_id`` is the document's key, so search hits map straight
back to document keys. The API key is read from config (env), never hardcoded.
"""

from __future__ import annotations

import json as jsonlib
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, cast

import httpx

from arvel_search.dtos import SearchResult
from arvel_search.engine import Engine
from arvel_search.exceptions import SearchError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Mapping, Sequence

    from arvel_search.dtos import SearchQuery

_NDJSON = "application/x-ndjson"


class ElasticsearchEngine(Engine):
    """Index and query documents through an Elasticsearch cluster."""

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
        lines: list[str] = []
        for document in documents:
            doc_id = str(document[key])
            lines.append(jsonlib.dumps({"index": {"_index": index, "_id": doc_id}}))
            lines.append(jsonlib.dumps(dict(document)))
        await self._bulk(lines)

    async def remove_documents(self, index: str, keys: Sequence[str]) -> None:
        lines = [jsonlib.dumps({"delete": {"_index": index, "_id": key}}) for key in keys]
        await self._bulk(lines)

    async def search(self, query: SearchQuery) -> SearchResult:
        body: dict[str, Any] = {"from": query.offset, "query": self._build_query(query)}
        if query.limit is not None:
            body["size"] = query.limit

        async with self._client() as client:
            payload = await self._request(client, "POST", f"/{query.index}/_search", json=body)

        hits_root = cast("dict[str, Any]", payload.get("hits", {}))
        hits = cast("list[dict[str, Any]]", hits_root.get("hits", []))
        ids = [str(hit["_id"]) for hit in hits if "_id" in hit]
        total = int(cast("dict[str, Any]", hits_root.get("total", {})).get("value", len(ids)))
        return SearchResult(ids=ids, total=total, raw=payload)

    async def flush(self, index: str) -> None:
        async with self._client() as client:
            await self._request(
                client,
                "POST",
                f"/{index}/_delete_by_query",
                json={"query": {"match_all": {}}},
            )

    async def delete_index(self, index: str) -> None:
        async with self._client() as client:
            await self._request(client, "DELETE", f"/{index}")

    @staticmethod
    def _build_query(query: SearchQuery) -> dict[str, Any]:
        match: dict[str, Any]
        if query.query:
            fields = list(query.columns) or ["*"]
            match = {"multi_match": {"query": query.query, "fields": fields}}
        else:
            match = {"match_all": {}}
        if not query.filters:
            return match
        terms = [{"term": {field_name: value}} for field_name, value in query.filters.items()]
        return {"bool": {"must": match, "filter": terms}}

    async def _bulk(self, lines: list[str]) -> None:
        if not lines:
            return
        ndjson = "\n".join(lines) + "\n"
        async with self._client() as client:
            await self._request(
                client,
                "POST",
                "/_bulk",
                content=ndjson,
                headers={"Content-Type": _NDJSON},
                params={"refresh": "true"},
            )

    @asynccontextmanager
    async def _client(self) -> AsyncGenerator[httpx.AsyncClient]:
        # An injected client is caller-owned — don't close it here.
        if self._http_client is not None:
            yield self._http_client
            return
        headers = {"Authorization": f"ApiKey {self._api_key}"} if self._api_key else {}
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
        content: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            response = await client.request(
                method, path, params=params, json=json, content=content, headers=headers
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"Elasticsearch request to {path} failed: {exc}"
            raise SearchError(msg) from exc
        if not response.content:
            return {}
        return cast("dict[str, Any]", response.json())


__all__ = ["ElasticsearchEngine"]
