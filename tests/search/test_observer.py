"""Tests for SearchObserver — auto-sync lifecycle hooks.

FR-025: SearchObserver.created() indexes the instance.
FR-025: SearchObserver.updated() re-indexes the instance.
FR-025: SearchObserver.deleted() removes the instance from the index.
FR-025: SearchObserver ignores non-Searchable models.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from arvel.search.mixin import Searchable
from arvel.search.observer import SearchObserver


def _make_searchable_instance(*, model_id: int = 1, index_name: str = "users") -> MagicMock:
    """Create a mock instance that acts as a Searchable model."""
    instance = MagicMock(spec=Searchable)
    instance.searchable_id.return_value = model_id
    instance.to_searchable_array.return_value = {"id": model_id, "name": "Alice"}
    instance.search_index_name.return_value = index_name

    # Make isinstance(instance, Searchable) return True
    instance.__class__ = type(
        "FakeSearchableModel",
        (Searchable,),
        {
            "__tablename__": "users",
            "__searchable__": ["name"],
        },
    )
    return instance


def _make_non_searchable_instance() -> MagicMock:
    """Create a mock instance that is NOT Searchable."""
    instance = MagicMock()
    instance.__class__ = type("PlainModel", (), {})
    return instance


class TestSearchObserverCreated:
    """FR-025: created() calls engine.upsert_documents."""

    async def test_indexes_searchable_instance(self) -> None:
        engine = AsyncMock()
        observer = SearchObserver(engine)
        instance = _make_searchable_instance()

        await observer.created(instance)
        engine.upsert_documents.assert_awaited_once()

    async def test_ignores_non_searchable_instance(self) -> None:
        engine = AsyncMock()
        observer = SearchObserver(engine)
        instance = _make_non_searchable_instance()

        await observer.created(instance)
        engine.upsert_documents.assert_not_awaited()


class TestSearchObserverUpdated:
    """FR-025: updated() re-indexes the instance."""

    async def test_reindexes_searchable_instance(self) -> None:
        engine = AsyncMock()
        observer = SearchObserver(engine)
        instance = _make_searchable_instance()

        await observer.updated(instance)
        engine.upsert_documents.assert_awaited_once()

    async def test_ignores_non_searchable_instance(self) -> None:
        engine = AsyncMock()
        observer = SearchObserver(engine)
        instance = _make_non_searchable_instance()

        await observer.updated(instance)
        engine.upsert_documents.assert_not_awaited()


class TestSearchObserverDeleted:
    """FR-025: deleted() removes the instance from the index."""

    async def test_removes_searchable_instance(self) -> None:
        engine = AsyncMock()
        observer = SearchObserver(engine)
        instance = _make_searchable_instance(model_id=42)

        await observer.deleted(instance)
        engine.remove_documents.assert_awaited_once()

    async def test_ignores_non_searchable_instance(self) -> None:
        engine = AsyncMock()
        observer = SearchObserver(engine)
        instance = _make_non_searchable_instance()

        await observer.deleted(instance)
        engine.remove_documents.assert_not_awaited()
