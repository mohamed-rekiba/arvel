"""Engine behavior — null, collection, and the REST drivers (httpx-mocked)."""

from __future__ import annotations

import json
from typing import Any

import httpx
from arvel_search.dtos import SearchQuery
from arvel_search.engines import (
    CollectionEngine,
    ElasticsearchEngine,
    MeilisearchEngine,
    NullEngine,
)


class TestNullEngine:
    async def test_writes_are_noops_and_search_empty(self) -> None:
        engine = NullEngine()
        await engine.upsert_documents("idx", [{"id": "1"}], key="id")
        await engine.remove_documents("idx", ["1"])
        result = await engine.search(SearchQuery(index="idx", query="anything"))
        assert result.ids == []
        assert result.total == 0


class TestCollectionEngine:
    async def test_upsert_and_substring_search(self) -> None:
        engine = CollectionEngine()
        await engine.upsert_documents(
            "articles",
            [{"id": "1", "title": "Python"}, {"id": "2", "title": "Rust"}],
            key="id",
        )

        result = await engine.search(SearchQuery(index="articles", query="pyth"))
        assert result.ids == ["1"]

    async def test_filters_apply(self) -> None:
        engine = CollectionEngine()
        await engine.upsert_documents(
            "articles",
            [{"id": "1", "title": "Go", "cat": "a"}, {"id": "2", "title": "Go", "cat": "b"}],
            key="id",
        )
        result = await engine.search(
            SearchQuery(index="articles", query="go", filters={"cat": "b"})
        )
        assert result.ids == ["2"]

    async def test_flush_clears_index(self) -> None:
        engine = CollectionEngine()
        await engine.upsert_documents("articles", [{"id": "1", "title": "x"}], key="id")
        await engine.flush("articles")
        result = await engine.search(SearchQuery(index="articles", query="x"))
        assert result.ids == []

    async def test_remove_deletes_keys(self) -> None:
        engine = CollectionEngine()
        await engine.upsert_documents("a", [{"id": "1", "t": "x"}, {"id": "2", "t": "x"}], key="id")
        await engine.remove_documents("a", ["1"])
        result = await engine.search(SearchQuery(index="a", query="x"))
        assert result.ids == ["2"]


def _meili_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search"):
            return httpx.Response(
                200,
                json={
                    "hits": [{"id": "7", "title": "Python"}, {"id": "9", "title": "Pytest"}],
                    "estimatedTotalHits": 2,
                },
            )
        return httpx.Response(202, json={"taskUid": 1})

    return httpx.MockTransport(handler)


class TestMeilisearchEngine:
    async def test_search_extracts_keys_and_total(self) -> None:
        client = httpx.AsyncClient(transport=_meili_transport(), base_url="http://meili")
        engine = MeilisearchEngine("http://meili", http_client=client)
        async with client:
            result = await engine.search(SearchQuery(index="articles", query="py"))
        assert result.ids == ["7", "9"]
        assert result.total == 2

    async def test_upsert_posts_documents(self) -> None:
        captured: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["path"] = request.url.path
            captured["primaryKey"] = request.url.params.get("primaryKey")
            captured["body"] = json.loads(request.content)
            return httpx.Response(202, json={"taskUid": 1})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://meili")
        engine = MeilisearchEngine("http://meili", http_client=client)
        async with client:
            await engine.upsert_documents("articles", [{"id": "1", "title": "x"}], key="id")

        assert captured["path"] == "/indexes/articles/documents"
        assert captured["primaryKey"] == "id"
        assert captured["body"] == [{"id": "1", "title": "x"}]


def _es_transport(captured: dict[str, Any]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/_search"):
            return httpx.Response(
                200,
                json={
                    "hits": {
                        "total": {"value": 1},
                        "hits": [{"_id": "42", "_source": {"title": "Python"}}],
                    }
                },
            )
        captured["bulk"] = request.content.decode()
        captured["content_type"] = request.headers.get("content-type")
        return httpx.Response(200, json={"errors": False, "items": []})

    return httpx.MockTransport(handler)


class TestElasticsearchEngine:
    async def test_search_reads_ids_from_hits(self) -> None:
        client = httpx.AsyncClient(transport=_es_transport({}), base_url="http://es")
        engine = ElasticsearchEngine("http://es", http_client=client)
        async with client:
            result = await engine.search(SearchQuery(index="articles", query="py"))
        assert result.ids == ["42"]
        assert result.total == 1

    async def test_upsert_sends_ndjson_bulk(self) -> None:
        captured: dict[str, Any] = {}
        client = httpx.AsyncClient(transport=_es_transport(captured), base_url="http://es")
        engine = ElasticsearchEngine("http://es", http_client=client)
        async with client:
            await engine.upsert_documents("articles", [{"id": "1", "title": "x"}], key="id")

        lines = [line for line in captured["bulk"].split("\n") if line]
        assert json.loads(lines[0]) == {"index": {"_index": "articles", "_id": "1"}}
        assert json.loads(lines[1]) == {"id": "1", "title": "x"}
        assert captured["content_type"] == "application/x-ndjson"
