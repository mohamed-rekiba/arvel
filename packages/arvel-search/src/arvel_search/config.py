"""Search configuration via ``SEARCH_*`` environment variables."""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class SearchConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    driver: str = Field(default="database", alias="SEARCH_DRIVER")
    index_prefix: str = Field(default="", alias="SEARCH_INDEX_PREFIX")

    # Whether lifecycle saves/deletes auto-sync the index. Off → call
    # searchable()/unsearchable() (or make_all_searchable) by hand.
    sync_on_save: bool = Field(default=True, alias="SEARCH_SYNC_ON_SAVE")

    # Push index sync onto the queue instead of running it inline on save.
    queue_sync: bool = Field(default=False, alias="SEARCH_QUEUE_SYNC")

    meilisearch_url: str = Field(default="http://localhost:7700", alias="SEARCH_MEILISEARCH_URL")
    meilisearch_key: SecretStr = Field(default=SecretStr(""), alias="SEARCH_MEILISEARCH_KEY")

    elasticsearch_url: str = Field(
        default="http://localhost:9200", alias="SEARCH_ELASTICSEARCH_URL"
    )
    elasticsearch_key: SecretStr = Field(default=SecretStr(""), alias="SEARCH_ELASTICSEARCH_KEY")


__all__ = ["SearchConfig"]
