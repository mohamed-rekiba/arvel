"""Tests for MeilisearchEngine — import guard and SDK interaction.

FR-008: MeilisearchEngine raises SearchConfigurationError when SDK is missing.
FR-008: MeilisearchEngine implements SearchEngine contract.
"""

from __future__ import annotations

from importlib import util
from unittest.mock import patch

import pytest

from arvel.search.contracts import SearchEngine
from arvel.search.exceptions import SearchConfigurationError

_has_meilisearch = util.find_spec("meilisearch_python_sdk") is not None
_requires_meilisearch = pytest.mark.skipif(
    not _has_meilisearch, reason="meilisearch-python-sdk not installed"
)


class TestMeilisearchImportGuard:
    """MeilisearchEngine raises a clear error when SDK is not installed."""

    def test_import_guard_raises_configuration_error(self) -> None:
        with patch.dict("sys.modules", {"meilisearch_python_sdk": None}):
            from arvel.search.drivers.meilisearch_driver import MeilisearchEngine

            with pytest.raises(SearchConfigurationError, match=r"[Mm]eilisearch"):
                MeilisearchEngine()


class TestMeilisearchEngineContract:
    """MeilisearchEngine implements SearchEngine."""

    @_requires_meilisearch
    def test_implements_search_engine(self) -> None:
        from arvel.search.drivers.meilisearch_driver import MeilisearchEngine

        assert issubclass(MeilisearchEngine, SearchEngine)

    @_requires_meilisearch
    def test_has_all_contract_methods(self) -> None:
        from arvel.search.drivers.meilisearch_driver import MeilisearchEngine

        for method in [
            "upsert_documents",
            "remove_documents",
            "search",
            "flush",
            "create_index",
            "delete_index",
        ]:
            assert hasattr(MeilisearchEngine, method)
