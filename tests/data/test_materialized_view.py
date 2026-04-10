"""Tests for Story 8: Materialized View Support.

Covers: FR-18 through FR-27, SEC-04.
All tests should FAIL until implementation exists.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import func, select

from .conftest import User


class TestMaterializedViewBase:
    """FR-18: MaterializedView is an abstract base class."""

    def test_materialized_view_importable(self) -> None:
        from arvel.data.materialized_view import MaterializedView

        assert MaterializedView is not None

    def test_materialized_view_is_abstract(self) -> None:
        from arvel.data.materialized_view import MaterializedView

        abstract_cls: type = MaterializedView
        with pytest.raises(TypeError):
            abstract_cls()

    def test_subclass_requires_query_method(self) -> None:
        from arvel.data.materialized_view import MaterializedView

        with pytest.raises(TypeError):

            class BadView(MaterializedView):
                __viewname__ = "bad_view"

            bad_cls: type = BadView
            bad_cls()

    def test_valid_subclass_has_query(self) -> None:
        from arvel.data.materialized_view import MaterializedView

        class GoodView(MaterializedView):
            __viewname__ = "good_view"

            @classmethod
            def query_definition(cls) -> Any:
                return select(func.count()).select_from(User.__table__)

        view = GoodView()
        assert view is not None
        stmt = GoodView.query_definition()
        assert stmt is not None


class TestViewRegistry:
    """FR-19: Views self-register in ViewRegistry."""

    def test_view_registry_importable(self) -> None:
        from arvel.data.materialized_view import ViewRegistry

        assert ViewRegistry is not None

    def test_register_and_get_views(self) -> None:
        from arvel.data.materialized_view import MaterializedView, ViewRegistry

        registry = ViewRegistry()

        class StatsView(MaterializedView):
            __viewname__ = "stats_view"

            @classmethod
            def query_definition(cls) -> Any:
                return select(func.count()).select_from(User.__table__)

        registry.register(StatsView)
        views = registry.all()
        assert any(v.__viewname__ == "stats_view" for v in views)

    def test_get_view_by_name(self) -> None:
        from arvel.data.materialized_view import MaterializedView, ViewRegistry

        registry = ViewRegistry()

        class NamedView(MaterializedView):
            __viewname__ = "named_view"

            @classmethod
            def query_definition(cls) -> Any:
                return select(func.count()).select_from(User.__table__)

        registry.register(NamedView)
        found = registry.get("named_view")
        assert found is NamedView

    def test_get_unknown_view_returns_none(self) -> None:
        from arvel.data.materialized_view import ViewRegistry

        registry = ViewRegistry()
        assert registry.get("nonexistent") is None


class TestMaterializedViewReadOnly:
    """FR-26: Materialized views are read-only (no insert/update/delete)."""

    def test_view_query_builder_is_read_only(self) -> None:
        from arvel.data.materialized_view import MaterializedView

        class ReadOnlyView(MaterializedView):
            __viewname__ = "readonly_view"

            @classmethod
            def query_definition(cls) -> Any:
                return select(func.count()).select_from(User.__table__)

        assert ReadOnlyView.readonly is True


class TestMaterializedViewRefresh:
    """FR-24, FR-25: View refresh commands."""

    async def test_refresh_single_view(self) -> None:
        from arvel.data.materialized_view import MaterializedView, ViewRegistry

        registry = ViewRegistry()

        class RefreshView(MaterializedView):
            __viewname__ = "refresh_view"

            @classmethod
            def query_definition(cls) -> Any:
                return select(func.count()).select_from(User.__table__)

        registry.register(RefreshView)
        result = await registry.refresh("refresh_view", db_url="sqlite+aiosqlite:///test.db")
        assert result is not None

    async def test_refresh_all_views(self) -> None:
        from arvel.data.materialized_view import MaterializedView, ViewRegistry

        registry = ViewRegistry()

        class ViewA(MaterializedView):
            __viewname__ = "view_a"

            @classmethod
            def query_definition(cls) -> Any:
                return select(func.count()).select_from(User.__table__)

        class ViewB(MaterializedView):
            __viewname__ = "view_b"

            @classmethod
            def query_definition(cls) -> Any:
                return select(func.count()).select_from(User.__table__)

        registry.register(ViewA)
        registry.register(ViewB)
        results = await registry.refresh_all(db_url="sqlite+aiosqlite:///test.db")
        assert len(results) == 2


class TestMaterializedViewImmutable:
    """FR-27, SEC-04: View definitions are immutable at runtime."""

    def test_viewname_is_class_level(self) -> None:
        from arvel.data.materialized_view import MaterializedView

        class ImmutableView(MaterializedView):
            __viewname__ = "immutable_view"

            @classmethod
            def query_definition(cls) -> Any:
                return select(func.count()).select_from(User.__table__)

        assert ImmutableView.__viewname__ == "immutable_view"


class TestPgIvmFallback:
    """FR-22, FR-23: pg_ivm detection and fallback."""

    def test_pg_ivm_detector_importable(self) -> None:
        from arvel.data.materialized_view import detect_pg_ivm

        assert callable(detect_pg_ivm)

    async def test_pg_ivm_not_available_on_sqlite(self) -> None:
        from arvel.data.materialized_view import detect_pg_ivm

        result = await detect_pg_ivm("sqlite+aiosqlite:///test.db")
        assert result is False
