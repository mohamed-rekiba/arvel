"""Search configuration — typed settings with SEARCH_ env prefix."""

from __future__ import annotations

from typing import ClassVar, Literal

from arvel.foundation.config import ModuleSettings


class SearchSettings(ModuleSettings):
    """Search driver configuration.

    All values can be overridden via environment variables prefixed
    with ``SEARCH_``:
      - ``SEARCH_DRIVER`` — which driver to use
      - ``SEARCH_PREFIX`` — optional index name prefix
      - ``SEARCH_MEILISEARCH_URL`` — Meilisearch server URL
      - ``SEARCH_MEILISEARCH_KEY`` — Meilisearch API key
      - ``SEARCH_ELASTICSEARCH_HOSTS`` — Elasticsearch host list
    """

    model_config: ClassVar[dict[str, str | bool]] = {
        "env_prefix": "SEARCH_",
        "extra": "ignore",
    }

    driver: Literal["null", "collection", "database", "meilisearch", "elasticsearch"] = "null"
    prefix: str = ""
    queue_sync: bool = False

    meilisearch_url: str = "http://localhost:7700"
    meilisearch_key: str = ""
    meilisearch_timeout: int = 5

    elasticsearch_hosts: str = "http://localhost:9200"
    elasticsearch_verify_certs: bool = True


settings_class = SearchSettings
