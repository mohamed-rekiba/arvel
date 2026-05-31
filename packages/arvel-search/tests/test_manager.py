"""SearchManager — driver resolution, custom drivers, and errors."""

from __future__ import annotations

import pytest
from arvel_search import SearchManager
from arvel_search.engine import Engine
from arvel_search.engines import (
    CollectionEngine,
    DatabaseEngine,
    ElasticsearchEngine,
    MeilisearchEngine,
    NullEngine,
)
from arvel_search.exceptions import UnknownSearchDriverError
from search_support import make_config


class TestDriverResolution:
    def test_default_driver_from_config(self) -> None:
        manager = SearchManager(make_config(driver="null"))
        assert isinstance(manager.create_driver(), NullEngine)

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("null", NullEngine),
            ("collection", CollectionEngine),
            ("database", DatabaseEngine),
            ("meilisearch", MeilisearchEngine),
            ("elasticsearch", ElasticsearchEngine),
        ],
    )
    def test_each_builtin_driver(self, name: str, expected: type[Engine]) -> None:
        manager = SearchManager(make_config())
        assert isinstance(manager.create_driver(name), expected)

    def test_engine_is_memoized(self) -> None:
        manager = SearchManager(make_config(driver="collection"))
        assert manager.create_driver() is manager.create_driver()

    def test_unknown_driver_raises_with_name(self) -> None:
        manager = SearchManager(make_config(driver="bogus"))
        with pytest.raises(UnknownSearchDriverError, match="bogus"):
            manager.create_driver()


class TestCustomDriver:
    def test_register_and_resolve_custom_driver(self) -> None:
        manager = SearchManager(make_config(driver="mine"))
        manager.register_driver("mine", NullEngine)
        assert isinstance(manager.create_driver(), NullEngine)

    def test_register_replaces_cached_instance(self) -> None:
        manager = SearchManager(make_config())
        first = manager.create_driver("collection")
        manager.register_driver("collection", CollectionEngine)
        assert manager.create_driver("collection") is not first
