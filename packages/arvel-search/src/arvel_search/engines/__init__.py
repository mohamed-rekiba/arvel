"""Built-in search engines."""

from __future__ import annotations

from arvel_search.engines.collection import CollectionEngine
from arvel_search.engines.database import DatabaseEngine
from arvel_search.engines.elasticsearch import ElasticsearchEngine
from arvel_search.engines.meilisearch import MeilisearchEngine
from arvel_search.engines.null import NullEngine

__all__ = [
    "CollectionEngine",
    "DatabaseEngine",
    "ElasticsearchEngine",
    "MeilisearchEngine",
    "NullEngine",
]
