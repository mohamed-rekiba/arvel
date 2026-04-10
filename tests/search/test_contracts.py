"""Tests for SearchEngine contract, data types, NullEngine, and CollectionEngine.

FR-001: SearchEngine ABC with upsert_documents, remove_documents, search, flush,
        create_index, delete_index.
FR-002: SearchHit dataclass with id and score fields.
FR-003: SearchResult dataclass with hits, total, and raw metadata.
FR-009: NullEngine implements SearchEngine (all methods are silent no-ops).
FR-010: CollectionEngine implements SearchEngine (in-memory indexing and search).
"""

from __future__ import annotations

import pytest

from arvel.search.contracts import SearchEngine, SearchHit, SearchResult


class TestSearchEngineContract:
    """FR-001: SearchEngine ABC defines required abstract methods."""

    def test_search_engine_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            SearchEngine()  # type: ignore[abstract]

    @pytest.mark.parametrize(
        "method",
        [
            "upsert_documents",
            "remove_documents",
            "search",
            "flush",
            "create_index",
            "delete_index",
        ],
    )
    def test_contract_has_method(self, method: str) -> None:
        assert hasattr(SearchEngine, method)


class TestSearchHit:
    """FR-002: SearchHit dataclass holds id and relevance score."""

    def test_create_with_defaults(self) -> None:
        hit = SearchHit(id=1)
        assert hit.id == 1
        assert hit.score == 0.0

    def test_create_with_score(self) -> None:
        hit = SearchHit(id="abc", score=0.95)
        assert hit.id == "abc"
        assert hit.score == 0.95

    def test_frozen(self) -> None:
        hit = SearchHit(id=1)
        with pytest.raises(AttributeError):
            hit.id = 2  # type: ignore[misc,ty:invalid-assignment]

    def test_string_id(self) -> None:
        hit = SearchHit(id="user_123", score=0.5)
        assert hit.id == "user_123"

    def test_integer_id(self) -> None:
        hit = SearchHit(id=42, score=1.0)
        assert hit.id == 42


class TestSearchResult:
    """FR-003: SearchResult wraps hits, total count, and raw metadata."""

    def test_create_with_defaults(self) -> None:
        result = SearchResult(hits=[], total=0)
        assert result.hits == []
        assert result.total == 0
        assert result.raw == {}

    def test_create_with_hits(self) -> None:
        hits = [SearchHit(id=1, score=0.9), SearchHit(id=2, score=0.7)]
        result = SearchResult(hits=hits, total=100)
        assert len(result.hits) == 2
        assert result.total == 100

    def test_create_with_raw_metadata(self) -> None:
        result = SearchResult(hits=[], total=0, raw={"processingTimeMs": 12})
        assert result.raw["processingTimeMs"] == 12

    def test_frozen(self) -> None:
        result = SearchResult(hits=[], total=0)
        with pytest.raises(AttributeError):
            result.total = 5  # type: ignore[misc,ty:invalid-assignment]


class TestNullEngine:
    """FR-009: NullEngine silently discards all operations."""

    async def test_null_implements_contract(self) -> None:
        from arvel.search.drivers.null_driver import NullEngine

        engine = NullEngine()
        assert isinstance(engine, SearchEngine)

    async def test_upsert_documents_no_op(self) -> None:
        from arvel.search.drivers.null_driver import NullEngine

        engine = NullEngine()
        await engine.upsert_documents("users", [{"id": 1, "name": "Alice"}])

    async def test_remove_documents_no_op(self) -> None:
        from arvel.search.drivers.null_driver import NullEngine

        engine = NullEngine()
        await engine.remove_documents("users", [1, 2, 3])

    async def test_search_returns_empty_result(self) -> None:
        from arvel.search.drivers.null_driver import NullEngine

        engine = NullEngine()
        result = await engine.search("users", "query")
        assert isinstance(result, SearchResult)
        assert result.hits == []
        assert result.total == 0

    async def test_flush_no_op(self) -> None:
        from arvel.search.drivers.null_driver import NullEngine

        engine = NullEngine()
        await engine.flush("users")

    async def test_create_index_no_op(self) -> None:
        from arvel.search.drivers.null_driver import NullEngine

        engine = NullEngine()
        await engine.create_index("users")

    async def test_delete_index_no_op(self) -> None:
        from arvel.search.drivers.null_driver import NullEngine

        engine = NullEngine()
        await engine.delete_index("users")


class TestCollectionEngine:
    """FR-010: CollectionEngine stores documents in memory and searches by string match."""

    async def test_collection_implements_contract(self) -> None:
        from arvel.search.drivers.collection_driver import CollectionEngine

        engine = CollectionEngine()
        assert isinstance(engine, SearchEngine)

    async def test_upsert_and_search(self) -> None:
        from arvel.search.drivers.collection_driver import CollectionEngine

        engine = CollectionEngine()
        await engine.create_index("users")
        await engine.upsert_documents(
            "users",
            [
                {"id": 1, "name": "Alice Johnson"},
                {"id": 2, "name": "Bob Smith"},
                {"id": 3, "name": "Alice Cooper"},
            ],
        )

        result = await engine.search("users", "Alice")
        assert result.total >= 2
        ids = [hit.id for hit in result.hits]
        assert 1 in ids
        assert 3 in ids

    async def test_search_empty_query_returns_all(self) -> None:
        from arvel.search.drivers.collection_driver import CollectionEngine

        engine = CollectionEngine()
        await engine.create_index("items")
        await engine.upsert_documents(
            "items",
            [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}],
        )

        result = await engine.search("items", "")
        assert result.total == 2

    async def test_search_with_filter(self) -> None:
        from arvel.search.drivers.collection_driver import CollectionEngine

        engine = CollectionEngine()
        await engine.create_index("users")
        await engine.upsert_documents(
            "users",
            [
                {"id": 1, "name": "Alice", "active": True},
                {"id": 2, "name": "Alice", "active": False},
            ],
        )

        result = await engine.search("users", "Alice", filters={"active": True})
        assert result.total == 1
        assert result.hits[0].id == 1

    async def test_search_with_limit_and_offset(self) -> None:
        from arvel.search.drivers.collection_driver import CollectionEngine

        engine = CollectionEngine()
        await engine.create_index("items")
        docs = [{"id": i, "name": f"Item {i}"} for i in range(10)]
        await engine.upsert_documents("items", docs)

        result = await engine.search("items", "", limit=3, offset=2)
        assert len(result.hits) == 3

    async def test_remove_documents(self) -> None:
        from arvel.search.drivers.collection_driver import CollectionEngine

        engine = CollectionEngine()
        await engine.create_index("users")
        await engine.upsert_documents(
            "users",
            [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
        )
        await engine.remove_documents("users", [1])

        result = await engine.search("users", "")
        assert result.total == 1
        assert result.hits[0].id == 2

    async def test_flush_clears_index(self) -> None:
        from arvel.search.drivers.collection_driver import CollectionEngine

        engine = CollectionEngine()
        await engine.create_index("users")
        await engine.upsert_documents("users", [{"id": 1, "name": "Alice"}])
        await engine.flush("users")

        result = await engine.search("users", "")
        assert result.total == 0

    async def test_delete_index(self) -> None:
        from arvel.search.drivers.collection_driver import CollectionEngine

        engine = CollectionEngine()
        await engine.create_index("temp")
        await engine.upsert_documents("temp", [{"id": 1, "name": "X"}])
        await engine.delete_index("temp")

        from arvel.search.exceptions import SearchIndexNotFoundError

        with pytest.raises(SearchIndexNotFoundError):
            await engine.search("temp", "X")

    async def test_create_index_idempotent(self) -> None:
        from arvel.search.drivers.collection_driver import CollectionEngine

        engine = CollectionEngine()
        await engine.create_index("users")
        await engine.create_index("users")

    async def test_delete_index_idempotent(self) -> None:
        from arvel.search.drivers.collection_driver import CollectionEngine

        engine = CollectionEngine()
        await engine.delete_index("nonexistent")

    async def test_upsert_updates_existing_document(self) -> None:
        from arvel.search.drivers.collection_driver import CollectionEngine

        engine = CollectionEngine()
        await engine.create_index("users")
        await engine.upsert_documents("users", [{"id": 1, "name": "Alice"}])
        await engine.upsert_documents("users", [{"id": 1, "name": "Alicia"}])

        result = await engine.search("users", "Alicia")
        assert result.total == 1
        assert result.hits[0].id == 1

    async def test_remove_nonexistent_ids_is_silent(self) -> None:
        from arvel.search.drivers.collection_driver import CollectionEngine

        engine = CollectionEngine()
        await engine.create_index("users")
        await engine.remove_documents("users", [999, 888])
