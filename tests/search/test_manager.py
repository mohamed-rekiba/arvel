"""Tests for SearchManager — driver resolution, unknown driver, custom drivers.

FR-008: SearchManager resolves configured driver from SearchSettings.
FR-008: SearchManager raises ConfigurationError for unknown driver names.
FR-008: SearchManager supports custom driver registration.
"""

from __future__ import annotations

from importlib import util
from typing import Literal

import pytest

from arvel.foundation.exceptions import ConfigurationError
from arvel.search.config import SearchSettings
from arvel.search.contracts import SearchEngine
from arvel.search.drivers.null_driver import NullEngine
from arvel.search.manager import SearchManager

_has_meilisearch_sdk = util.find_spec("meilisearch_python_sdk") is not None
_has_elasticsearch = util.find_spec("elasticsearch") is not None


class TestSearchManagerBuiltinDrivers:
    """FR-008: SearchManager resolves built-in drivers from settings."""

    def test_resolve_null_driver(self) -> None:
        manager = SearchManager()
        driver_name: Literal["null"] = "null"
        settings = SearchSettings(driver=driver_name)
        driver = manager.create_driver(settings)
        assert isinstance(driver, NullEngine)

    def test_resolve_collection_driver(self) -> None:
        from arvel.search.drivers.collection_driver import CollectionEngine

        manager = SearchManager()
        driver_name: Literal["collection"] = "collection"
        settings = SearchSettings(driver=driver_name)
        driver = manager.create_driver(settings)
        assert isinstance(driver, CollectionEngine)

    def test_default_settings_returns_null(self) -> None:
        manager = SearchManager()
        driver = manager.create_driver()
        assert isinstance(driver, NullEngine)

    @pytest.mark.skipif(not _has_meilisearch_sdk, reason="meilisearch-python-sdk not installed")
    def test_resolve_meilisearch_driver(self) -> None:
        manager = SearchManager()
        settings = SearchSettings(driver="meilisearch", meilisearch_url="http://localhost:7700")
        driver = manager.create_driver(settings)
        assert isinstance(driver, SearchEngine)
        assert type(driver).__name__ == "MeilisearchEngine"

    @pytest.mark.skipif(not _has_elasticsearch, reason="elasticsearch not installed")
    def test_resolve_elasticsearch_driver(self) -> None:
        manager = SearchManager()
        settings = SearchSettings(
            driver="elasticsearch", elasticsearch_hosts="http://localhost:9200"
        )
        driver = manager.create_driver(settings)
        assert isinstance(driver, SearchEngine)
        assert type(driver).__name__ == "ElasticsearchEngine"


class TestSearchManagerUnknownDriver:
    """FR-008: SearchManager raises ConfigurationError for unknown drivers."""

    def test_unknown_driver_raises_configuration_error(self) -> None:
        manager = SearchManager()
        settings = SearchSettings.model_construct(driver="nonexistent")

        with pytest.raises(ConfigurationError, match=r"[Uu]nknown.*search.*driver"):
            manager.create_driver(settings)

    def test_error_message_lists_available_drivers(self) -> None:
        manager = SearchManager()
        settings = SearchSettings.model_construct(driver="bad")

        with pytest.raises(ConfigurationError, match="null"):
            manager.create_driver(settings)


class TestSearchManagerCustomDrivers:
    """FR-008: SearchManager supports registering custom drivers."""

    def test_register_and_resolve_custom_driver(self) -> None:
        manager = SearchManager()
        custom_engine = NullEngine()
        manager.register_driver("custom", lambda _settings: custom_engine)

        settings = SearchSettings.model_construct(driver="custom")
        driver = manager.create_driver(settings)
        assert driver is custom_engine

    def test_custom_driver_overrides_builtin(self) -> None:
        manager = SearchManager()
        override = NullEngine()
        manager.register_driver("null", lambda _settings: override)

        driver_name: Literal["null"] = "null"
        settings = SearchSettings(driver=driver_name)
        driver = manager.create_driver(settings)
        assert driver is override
