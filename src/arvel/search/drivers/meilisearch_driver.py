"""MeilisearchEngine — driver for Meilisearch via meilisearch-python-sdk.

Requires the optional ``meilisearch`` extra:
``pip install arvel[meilisearch]``
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING, Any

from arvel.search.contracts import SearchEngine
from arvel.search.exceptions import SearchConfigurationError

if TYPE_CHECKING:
    from arvel.search.contracts import SearchResult


def _require_meilisearch() -> None:
    if importlib.util.find_spec("meilisearch_python_sdk") is None:
        raise SearchConfigurationError(
            "Meilisearch SDK is not installed. Install with: pip install arvel[meilisearch]",
            engine="meilisearch",
            detail="meilisearch-python-sdk package is required",
        )


class MeilisearchEngine(SearchEngine):
    """Search engine backed by a Meilisearch server.

    Uses ``meilisearch-python-sdk`` (async client). The SDK import is
    guarded — ``SearchConfigurationError`` is raised if the package
    isn't installed.
    """

    def __init__(
        self,
        url: str = "http://localhost:7700",
        api_key: str = "",
        timeout: int = 5,
    ) -> None:
        _require_meilisearch()
        self._url = url
        self._api_key = api_key
        self._timeout = timeout

    async def upsert_documents(
        self,
        index: str,
        documents: list[dict[str, Any]],
        primary_key: str = "id",
    ) -> None:
        raise NotImplementedError

    async def remove_documents(self, index: str, ids: list[str | int]) -> None:
        raise NotImplementedError

    async def search(
        self,
        index: str,
        query: str,
        *,
        filters: dict[str, Any] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> SearchResult:
        raise NotImplementedError

    async def flush(self, index: str) -> None:
        raise NotImplementedError

    async def create_index(self, index: str, *, primary_key: str = "id") -> None:
        raise NotImplementedError

    async def delete_index(self, index: str) -> None:
        raise NotImplementedError
