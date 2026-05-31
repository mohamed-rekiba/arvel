"""SearchFake — an in-memory engine that records writes for test assertions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel_search.engines.collection import CollectionEngine

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


class SearchFake(CollectionEngine):
    """Drop-in engine for tests.

    Behaves like :class:`CollectionEngine` for reads, but also records every
    indexed and removed document key so tests can assert on sync behavior
    without a running search server. Activate via ``Search.fake()``.
    """

    def __init__(self) -> None:
        super().__init__()
        self.indexed: list[tuple[str, str]] = []
        self.removed: list[tuple[str, str]] = []

    async def upsert_documents(
        self, index: str, documents: Sequence[Mapping[str, Any]], *, key: str
    ) -> None:
        await super().upsert_documents(index, documents, key=key)
        self.indexed.extend((index, str(doc[key])) for doc in documents)

    async def remove_documents(self, index: str, keys: Sequence[str]) -> None:
        await super().remove_documents(index, keys)
        self.removed.extend((index, key) for key in keys)

    def assert_indexed(self, model: Any) -> None:
        entry = (model.search_index_name(), str(model.searchable_id()))
        if entry not in self.indexed:
            msg = f"Expected {entry} to be indexed, but it wasn't. Indexed: {self.indexed}"
            raise AssertionError(msg)

    def assert_not_indexed(self, model: Any) -> None:
        entry = (model.search_index_name(), str(model.searchable_id()))
        if entry in self.indexed:
            msg = f"Expected {entry} not to be indexed, but it was."
            raise AssertionError(msg)

    def assert_removed(self, model: Any) -> None:
        entry = (model.search_index_name(), str(model.searchable_id()))
        if entry not in self.removed:
            msg = f"Expected {entry} to be removed, but it wasn't. Removed: {self.removed}"
            raise AssertionError(msg)

    def assert_nothing_indexed(self) -> None:
        if self.indexed:
            msg = f"Expected nothing indexed, but found: {self.indexed}"
            raise AssertionError(msg)

    def assert_indexed_count(self, count: int) -> None:
        actual = len(self.indexed)
        if actual != count:
            msg = f"Expected {count} documents indexed, found {actual}."
            raise AssertionError(msg)

    def reset(self) -> None:
        self.indexed.clear()
        self.removed.clear()
        self._store.clear()


__all__ = ["SearchFake"]
