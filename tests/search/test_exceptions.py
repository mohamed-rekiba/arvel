"""Tests for search exception hierarchy.

FR-004: SearchEngineError base error with engine attribute.
FR-005: SearchIndexNotFoundError with engine and index attributes.
FR-006: SearchConnectionError with engine and url attributes.
FR-007: SearchConfigurationError with engine and detail attributes.
"""

from __future__ import annotations

import pytest

from arvel.foundation.exceptions import ArvelError
from arvel.search.exceptions import (
    SearchConfigurationError,
    SearchConnectionError,
    SearchEngineError,
    SearchIndexNotFoundError,
)


class TestSearchEngineError:
    """FR-004: Base error for all search engine failures."""

    def test_inherits_arvel_error(self) -> None:
        assert issubclass(SearchEngineError, ArvelError)

    def test_message_and_engine(self) -> None:
        err = SearchEngineError("something failed", engine="meilisearch")
        assert str(err) == "something failed"
        assert err.engine == "meilisearch"

    def test_catchable_as_arvel_error(self) -> None:
        with pytest.raises(ArvelError):
            raise SearchEngineError("fail", engine="null")


class TestSearchIndexNotFoundError:
    """FR-005: Error for operations on non-existent indexes."""

    def test_inherits_search_engine_error(self) -> None:
        assert issubclass(SearchIndexNotFoundError, SearchEngineError)

    def test_index_attribute(self) -> None:
        err = SearchIndexNotFoundError(
            "Index 'users' not found", engine="meilisearch", index="users"
        )
        assert err.index == "users"
        assert err.engine == "meilisearch"


class TestSearchConnectionError:
    """FR-006: Error when the driver can't reach the search engine."""

    def test_inherits_search_engine_error(self) -> None:
        assert issubclass(SearchConnectionError, SearchEngineError)

    def test_url_attribute(self) -> None:
        err = SearchConnectionError(
            "Connection refused", engine="elasticsearch", url="http://localhost:9200"
        )
        assert err.url == "http://localhost:9200"
        assert err.engine == "elasticsearch"


class TestSearchConfigurationError:
    """FR-007: Error for misconfigured drivers (e.g., missing SDK)."""

    def test_inherits_search_engine_error(self) -> None:
        assert issubclass(SearchConfigurationError, SearchEngineError)

    def test_detail_attribute(self) -> None:
        err = SearchConfigurationError(
            "Meilisearch SDK not installed",
            engine="meilisearch",
            detail="pip install arvel[meilisearch]",
        )
        assert err.detail == "pip install arvel[meilisearch]"
        assert err.engine == "meilisearch"
