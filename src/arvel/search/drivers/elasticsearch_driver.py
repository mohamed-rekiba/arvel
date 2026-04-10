"""ElasticsearchEngine — driver for Elasticsearch via the official async client.

Requires the optional ``elasticsearch`` extra:
``pip install arvel[elasticsearch]``
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING, Any

from arvel.search.contracts import SearchEngine
from arvel.search.exceptions import SearchConfigurationError

if TYPE_CHECKING:
    from arvel.search.contracts import SearchResult


def _require_elasticsearch() -> None:
    if importlib.util.find_spec("elasticsearch") is None:
        raise SearchConfigurationError(
            "Elasticsearch SDK is not installed. Install with: pip install arvel[elasticsearch]",
            engine="elasticsearch",
            detail="elasticsearch[async] package is required",
        )


class ElasticsearchEngine(SearchEngine):
    """Search engine backed by an Elasticsearch cluster.

    Uses ``elasticsearch[async]`` (official client). The SDK import is
    guarded — ``SearchConfigurationError`` is raised if the package
    isn't installed.
    """

    def __init__(
        self,
        hosts: str = "http://localhost:9200",
        verify_certs: bool = True,
    ) -> None:
        _require_elasticsearch()
        self._hosts = hosts
        self._verify_certs = verify_certs

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
