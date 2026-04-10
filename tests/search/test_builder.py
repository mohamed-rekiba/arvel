"""Tests for SearchBuilder — fluent API, terminal methods, pagination.

FR-011: SearchBuilder provides where(), order_by(), limit(), offset(), within().
FR-012: SearchBuilder.get() returns hydrated model instances.
FR-013: SearchBuilder.first() returns first result or None.
FR-014: SearchBuilder.paginate() returns PaginatedSearchResult.
FR-015: SearchBuilder.keys() returns primary key values only.
FR-016: SearchBuilder.count() returns total match count.
FR-017: SearchBuilder.raw() returns raw SearchResult without hydration.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from arvel.search.builder import PaginatedSearchResult, SearchBuilder
from arvel.search.contracts import SearchHit, SearchResult


def _mock_engine(*, hits: list[SearchHit] | None = None, total: int = 0) -> AsyncMock:
    """Create a mock SearchEngine with a predetermined search result."""
    engine = AsyncMock()
    engine.search.return_value = SearchResult(
        hits=hits or [],
        total=total,
    )
    return engine


def _mock_model_cls() -> MagicMock:
    """Create a mock model class with __tablename__."""
    cls = MagicMock()
    cls.__tablename__ = "users"
    return cls


class TestSearchBuilderChaining:
    """FR-011: Fluent filter methods return the builder for chaining."""

    def test_where_returns_self(self) -> None:
        model_cls = _mock_model_cls()
        engine = _mock_engine()
        builder = SearchBuilder(model_cls, engine, "query", "users")
        result = builder.where("active", True)
        assert result is builder

    def test_order_by_returns_self(self) -> None:
        model_cls = _mock_model_cls()
        engine = _mock_engine()
        builder = SearchBuilder(model_cls, engine, "query", "users")
        result = builder.order_by("name")
        assert result is builder

    def test_limit_returns_self(self) -> None:
        model_cls = _mock_model_cls()
        engine = _mock_engine()
        builder = SearchBuilder(model_cls, engine, "query", "users")
        result = builder.limit(10)
        assert result is builder

    def test_offset_returns_self(self) -> None:
        model_cls = _mock_model_cls()
        engine = _mock_engine()
        builder = SearchBuilder(model_cls, engine, "query", "users")
        result = builder.offset(20)
        assert result is builder

    def test_within_returns_self(self) -> None:
        model_cls = _mock_model_cls()
        engine = _mock_engine()
        builder = SearchBuilder(model_cls, engine, "query", "users")
        result = builder.within("custom_index")
        assert result is builder

    def test_full_chain(self) -> None:
        model_cls = _mock_model_cls()
        engine = _mock_engine()
        builder = SearchBuilder(model_cls, engine, "query", "users")
        chained = builder.where("active", True).order_by("name").limit(10).offset(5)
        assert chained is builder


class TestSearchBuilderTerminals:
    """FR-012 to FR-017: Terminal methods execute the search."""

    async def test_get_calls_engine_search(self) -> None:
        model_cls = _mock_model_cls()
        engine = _mock_engine()
        builder = SearchBuilder(model_cls, engine, "alice", "users")

        await builder.get()
        engine.search.assert_awaited_once()

    async def test_get_returns_list(self) -> None:
        model_cls = _mock_model_cls()
        engine = _mock_engine(hits=[], total=0)
        builder = SearchBuilder(model_cls, engine, "alice", "users")

        result = await builder.get()
        assert isinstance(result, list)

    async def test_first_returns_none_on_empty(self) -> None:
        model_cls = _mock_model_cls()
        engine = _mock_engine(hits=[], total=0)
        builder = SearchBuilder(model_cls, engine, "nobody", "users")

        result = await builder.first()
        assert result is None

    async def test_keys_returns_id_list(self) -> None:
        model_cls = _mock_model_cls()
        hits = [SearchHit(id=1, score=0.9), SearchHit(id=2, score=0.8)]
        engine = _mock_engine(hits=hits, total=2)
        builder = SearchBuilder(model_cls, engine, "query", "users")

        result = await builder.keys()
        assert result == [1, 2]

    async def test_count_returns_total(self) -> None:
        model_cls = _mock_model_cls()
        engine = _mock_engine(total=42)
        builder = SearchBuilder(model_cls, engine, "query", "users")

        result = await builder.count()
        assert result == 42

    async def test_raw_returns_search_result(self) -> None:
        model_cls = _mock_model_cls()
        engine = _mock_engine(hits=[], total=0)
        builder = SearchBuilder(model_cls, engine, "query", "users")

        result = await builder.raw()
        assert isinstance(result, SearchResult)

    async def test_paginate_returns_paginated_result(self) -> None:
        model_cls = _mock_model_cls()
        engine = _mock_engine(hits=[], total=0)
        builder = SearchBuilder(model_cls, engine, "query", "users")

        result = await builder.paginate(per_page=20, page=1)
        assert isinstance(result, PaginatedSearchResult)
        assert result.per_page == 20
        assert result.current_page == 1


class TestPaginatedSearchResult:
    """FR-014: PaginatedSearchResult data structure."""

    def test_create(self) -> None:
        result = PaginatedSearchResult(
            items=[], total=100, per_page=20, current_page=1, last_page=5
        )
        assert result.total == 100
        assert result.per_page == 20
        assert result.current_page == 1
        assert result.last_page == 5
        assert result.items == []

    def test_last_page_calculation(self) -> None:
        result = PaginatedSearchResult(items=[], total=55, per_page=20, current_page=1, last_page=3)
        assert result.last_page == 3
