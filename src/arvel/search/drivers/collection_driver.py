"""CollectionEngine — in-memory search for dev/testing."""

from __future__ import annotations

from typing import Any

from arvel.search.contracts import SearchEngine, SearchHit, SearchResult
from arvel.search.exceptions import SearchIndexNotFoundError


class CollectionEngine(SearchEngine):
    """In-memory search engine that filters documents with string matching.

    Useful for development and testing when no external engine is available.
    Documents are stored in a plain dict keyed by index name.
    """

    def __init__(self) -> None:
        self._indexes: dict[str, dict[str | int, dict[str, Any]]] = {}

    def _require_index(self, index: str) -> dict[str | int, dict[str, Any]]:
        if index not in self._indexes:
            raise SearchIndexNotFoundError(
                f"Index '{index}' not found",
                engine="collection",
                index=index,
            )
        return self._indexes[index]

    async def upsert_documents(
        self,
        index: str,
        documents: list[dict[str, Any]],
        primary_key: str = "id",
    ) -> None:
        if index not in self._indexes:
            self._indexes[index] = {}
        store = self._indexes[index]
        for doc in documents:
            doc_id = doc[primary_key]
            store[doc_id] = doc

    async def remove_documents(self, index: str, ids: list[str | int]) -> None:
        if index not in self._indexes:
            return
        store = self._indexes[index]
        for doc_id in ids:
            store.pop(doc_id, None)

    async def search(
        self,
        index: str,
        query: str,
        *,
        filters: dict[str, Any] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> SearchResult:
        store = self._require_index(index)
        matched: list[tuple[str | int, float]] = []

        query_lower = query.lower()
        for doc_id, doc in store.items():
            if filters:
                skip = False
                for fk, fv in filters.items():
                    if doc.get(fk) != fv:
                        skip = True
                        break
                if skip:
                    continue

            if not query_lower:
                matched.append((doc_id, 0.0))
                continue

            for value in doc.values():
                if isinstance(value, str) and query_lower in value.lower():
                    matched.append((doc_id, 1.0))
                    break

        total = len(matched)
        page = matched[offset : offset + limit]
        hits = [SearchHit(id=doc_id, score=score) for doc_id, score in page]
        return SearchResult(hits=hits, total=total)

    async def flush(self, index: str) -> None:
        if index in self._indexes:
            self._indexes[index].clear()

    async def create_index(self, index: str, *, primary_key: str = "id") -> None:
        if index not in self._indexes:
            self._indexes[index] = {}

    async def delete_index(self, index: str) -> None:
        self._indexes.pop(index, None)
