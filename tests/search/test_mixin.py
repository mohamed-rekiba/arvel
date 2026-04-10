"""Tests for Searchable mixin — model integration.

FR-019: Searchable mixin adds search() class method.
FR-020: to_searchable_array() uses __searchable__ columns.
FR-021: searchable_id() returns the model's primary key.
FR-022: search_index_name() defaults to __tablename__.
FR-023: search_index_name() uses __search_index__ override when set.
FR-024: search() returns a SearchBuilder[T].
"""

from __future__ import annotations

from typing import ClassVar

from arvel.search.mixin import Searchable


class TestSearchableMixinAttributes:
    """FR-019: Searchable mixin class attributes."""

    def test_has_searchable_attribute(self) -> None:
        assert hasattr(Searchable, "__searchable__")

    def test_has_search_index_attribute(self) -> None:
        assert hasattr(Searchable, "__search_index__")

    def test_search_index_default_is_none(self) -> None:
        assert Searchable.__search_index__ is None


class TestSearchableMethods:
    """FR-020 to FR-024: Searchable mixin methods."""

    def test_has_search_method(self) -> None:
        assert hasattr(Searchable, "search")
        assert callable(Searchable.search)

    def test_has_to_searchable_array(self) -> None:
        assert hasattr(Searchable, "to_searchable_array")
        assert callable(Searchable.to_searchable_array)

    def test_has_searchable_id(self) -> None:
        assert hasattr(Searchable, "searchable_id")
        assert callable(Searchable.searchable_id)

    def test_has_search_index_name(self) -> None:
        assert hasattr(Searchable, "search_index_name")
        assert callable(Searchable.search_index_name)

    def test_has_search_index_method(self) -> None:
        assert hasattr(Searchable, "search_index")
        assert callable(Searchable.search_index)

    def test_has_search_remove_method(self) -> None:
        assert hasattr(Searchable, "search_remove")
        assert callable(Searchable.search_remove)


class TestSearchableSearchIndexName:
    """FR-022/FR-023: Index name resolution."""

    def test_default_index_name_uses_tablename(self) -> None:
        class FakeModel(Searchable):
            __tablename__ = "users"
            __searchable__: ClassVar[list[str]] = ["name", "email"]

        assert FakeModel.search_index_name() == "users"

    def test_custom_index_name_overrides_tablename(self) -> None:
        class FakeModel(Searchable):
            __tablename__ = "users"
            __searchable__: ClassVar[list[str]] = ["name"]
            __search_index__ = "custom_users"

        assert FakeModel.search_index_name() == "custom_users"


class TestSearchableToSearchableArray:
    """FR-020: to_searchable_array() builds document from __searchable__ columns."""

    def test_returns_dict_with_searchable_fields(self) -> None:
        class FakeModel(Searchable):
            __tablename__ = "users"
            __searchable__: ClassVar[list[str]] = ["name", "email"]

            def __init__(self) -> None:
                self.id = 1
                self.name = "Alice"
                self.email = "alice@example.com"
                self.password = "secret"

        model = FakeModel()
        doc = model.to_searchable_array()

        assert isinstance(doc, dict)
        assert "name" in doc
        assert "email" in doc
        assert doc["name"] == "Alice"
        assert "password" not in doc

    def test_includes_primary_key(self) -> None:
        class FakeModel(Searchable):
            __tablename__ = "users"
            __searchable__: ClassVar[list[str]] = ["name"]

            def __init__(self) -> None:
                self.id = 42
                self.name = "Bob"

        model = FakeModel()
        doc = model.to_searchable_array()
        assert "id" in doc
        assert doc["id"] == 42


class TestSearchableSearchableId:
    """FR-021: searchable_id() returns the primary key value."""

    def test_returns_id(self) -> None:
        class FakeModel(Searchable):
            __tablename__ = "users"
            __searchable__: ClassVar[list[str]] = ["name"]

            def __init__(self) -> None:
                self.id = 99
                self.name = "Charlie"

        model = FakeModel()
        assert model.searchable_id() == 99
