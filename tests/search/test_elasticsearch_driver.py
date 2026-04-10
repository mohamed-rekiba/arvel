"""Tests for ElasticsearchEngine — import guard and SDK interaction.

FR-008: ElasticsearchEngine raises SearchConfigurationError when SDK is missing.
FR-008: ElasticsearchEngine implements SearchEngine contract.
"""

from __future__ import annotations

from importlib import util
from unittest.mock import patch

import pytest

from arvel.search.contracts import SearchEngine
from arvel.search.exceptions import SearchConfigurationError

_has_elasticsearch = util.find_spec("elasticsearch") is not None
_requires_elasticsearch = pytest.mark.skipif(
    not _has_elasticsearch, reason="elasticsearch not installed"
)


class TestElasticsearchImportGuard:
    """ElasticsearchEngine raises a clear error when SDK is not installed."""

    def test_import_guard_raises_configuration_error(self) -> None:
        with patch.dict("sys.modules", {"elasticsearch": None}):
            from arvel.search.drivers.elasticsearch_driver import ElasticsearchEngine

            with pytest.raises(SearchConfigurationError, match=r"[Ee]lasticsearch"):
                ElasticsearchEngine()


class TestElasticsearchEngineContract:
    """ElasticsearchEngine implements SearchEngine."""

    @_requires_elasticsearch
    def test_implements_search_engine(self) -> None:
        from arvel.search.drivers.elasticsearch_driver import ElasticsearchEngine

        assert issubclass(ElasticsearchEngine, SearchEngine)

    @_requires_elasticsearch
    def test_has_all_contract_methods(self) -> None:
        from arvel.search.drivers.elasticsearch_driver import ElasticsearchEngine

        for method in [
            "upsert_documents",
            "remove_documents",
            "search",
            "flush",
            "create_index",
            "delete_index",
        ]:
            assert hasattr(ElasticsearchEngine, method)
