"""Tests for SearchSettings — SEARCH_ env prefix.

NFR-010: SearchSettings uses SEARCH_ env prefix for all configuration.
"""

from __future__ import annotations

import os
from unittest.mock import patch


class TestSearchSettingsDefaults:
    """NFR-010: Default values when no SEARCH_ env vars are set."""

    def test_defaults(self, clean_search_env: None) -> None:
        from arvel.search.config import SearchSettings

        settings = SearchSettings()
        assert settings.driver == "null"
        assert settings.prefix == ""
        assert settings.queue_sync is False
        assert settings.meilisearch_url == "http://localhost:7700"
        assert settings.meilisearch_key == ""
        assert settings.meilisearch_timeout == 5
        assert settings.elasticsearch_hosts == "http://localhost:9200"
        assert settings.elasticsearch_verify_certs is True


class TestSearchSettingsEnvOverride:
    """NFR-010: Environment variables with SEARCH_ prefix override defaults."""

    def test_driver_override(self) -> None:
        from arvel.search.config import SearchSettings

        with patch.dict(os.environ, {"SEARCH_DRIVER": "meilisearch"}):
            settings = SearchSettings()
            assert settings.driver == "meilisearch"

    def test_meilisearch_config_override(self) -> None:
        from arvel.search.config import SearchSettings

        with patch.dict(
            os.environ,
            {
                "SEARCH_MEILISEARCH_URL": "http://meili:7700",
                "SEARCH_MEILISEARCH_KEY": "secret-key",
                "SEARCH_MEILISEARCH_TIMEOUT": "10",
            },
        ):
            settings = SearchSettings()
            assert settings.meilisearch_url == "http://meili:7700"
            assert settings.meilisearch_key == "secret-key"
            assert settings.meilisearch_timeout == 10

    def test_elasticsearch_config_override(self) -> None:
        from arvel.search.config import SearchSettings

        with patch.dict(
            os.environ,
            {
                "SEARCH_ELASTICSEARCH_HOSTS": "http://es1:9200,http://es2:9200",
                "SEARCH_ELASTICSEARCH_VERIFY_CERTS": "false",
            },
        ):
            settings = SearchSettings()
            assert settings.elasticsearch_hosts == "http://es1:9200,http://es2:9200"
            assert settings.elasticsearch_verify_certs is False

    def test_prefix_and_queue_sync(self) -> None:
        from arvel.search.config import SearchSettings

        with patch.dict(
            os.environ,
            {"SEARCH_PREFIX": "myapp_", "SEARCH_QUEUE_SYNC": "true"},
        ):
            settings = SearchSettings()
            assert settings.prefix == "myapp_"
            assert settings.queue_sync is True
