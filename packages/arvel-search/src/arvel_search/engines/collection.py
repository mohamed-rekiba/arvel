"""Collection engine — in-memory index. Great for tests and tiny datasets."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel_search.dtos import SearchResult
from arvel_search.engine import Engine

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from arvel_search.dtos import SearchQuery


class CollectionEngine(Engine):
    """Keeps documents in a per-index dict and scans them with substring match.

    Matching is case-insensitive across every stringified value in the payload.
    Filters are exact-equality on the indexed value. Linear in document count —
    not for production scale — but it needs no server and is fully deterministic,
    which makes it ideal for tests and local dev. In-memory only; never persisted.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, dict[str, Any]]] = {}

    async def upsert_documents(
        self, index: str, documents: Sequence[Mapping[str, Any]], *, key: str
    ) -> None:
        bucket = self._store.setdefault(index, {})
        for document in documents:
            bucket[str(document[key])] = dict(document)

    async def remove_documents(self, index: str, keys: Sequence[str]) -> None:
        bucket = self._store.get(index)
        if bucket is None:
            return
        for key in keys:
            bucket.pop(key, None)

    async def search(self, query: SearchQuery) -> SearchResult:
        bucket = self._store.get(query.index, {})
        needle = query.query.casefold()

        matches = [
            key
            for key, doc in bucket.items()
            if self._passes_filters(doc, query.filters) and self._matches(doc, needle)
        ]
        total = len(matches)

        end = None if query.limit is None else query.offset + query.limit
        page = matches[query.offset : end]
        return SearchResult(ids=page, total=total, raw=list(page))

    async def flush(self, index: str) -> None:
        self._store.pop(index, None)

    @staticmethod
    def _matches(doc: dict[str, Any], needle: str) -> bool:
        if not needle:
            return True
        return any(needle in str(value).casefold() for value in doc.values())

    @staticmethod
    def _passes_filters(doc: dict[str, Any], filters: Any) -> bool:
        return all(doc.get(field_name) == value for field_name, value in filters.items())


__all__ = ["CollectionEngine"]
