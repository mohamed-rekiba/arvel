"""Tests for arvel.support.utils — data_get type-safe nested access."""

from __future__ import annotations

from dataclasses import dataclass

from arvel.support.utils import data_get


class TestDataGetDict:
    """Dict traversal at various depths."""

    def test_single_key(self) -> None:
        assert data_get({"a": 1}, "a") == 1

    def test_two_levels(self) -> None:
        assert data_get({"a": {"b": 2}}, "a.b") == 2

    def test_three_levels(self) -> None:
        assert data_get({"a": {"b": {"c": 3}}}, "a.b.c") == 3

    def test_missing_key_returns_none(self) -> None:
        assert data_get({"a": 1}, "b") is None

    def test_missing_key_returns_default(self) -> None:
        assert data_get({"a": 1}, "b", "fallback") == "fallback"

    def test_missing_nested_key_returns_default(self) -> None:
        assert data_get({"a": {"b": 1}}, "a.c", 42) == 42

    def test_none_value_in_chain_returns_default(self) -> None:
        assert data_get({"a": None}, "a.b", "nope") == "nope"

    def test_empty_path_returns_data(self) -> None:
        d = {"a": 1}
        assert data_get(d, "") is d

    def test_preserves_falsy_values(self) -> None:
        assert data_get({"a": 0}, "a") == 0
        assert data_get({"a": ""}, "a") == ""
        assert data_get({"a": False}, "a") is False
        assert data_get({"a": []}, "a") == []

    def test_none_data_returns_default(self) -> None:
        assert data_get(None, "a.b", "safe") == "safe"


class TestDataGetList:
    """List index traversal."""

    def test_list_index(self) -> None:
        assert data_get({"items": [10, 20, 30]}, "items.1") == 20

    def test_list_first_element(self) -> None:
        assert data_get({"items": ["a", "b"]}, "items.0") == "a"

    def test_nested_dict_in_list(self) -> None:
        data = {"users": [{"name": "Alice"}, {"name": "Bob"}]}
        assert data_get(data, "users.0.name") == "Alice"
        assert data_get(data, "users.1.name") == "Bob"

    def test_out_of_bounds_returns_default(self) -> None:
        assert data_get({"items": [1, 2]}, "items.99", -1) == -1

    def test_non_numeric_segment_on_list_returns_default(self) -> None:
        assert data_get({"items": [1, 2]}, "items.name", "nope") == "nope"

    def test_deeply_nested_list(self) -> None:
        data = {"a": [{"b": [{"c": "deep"}]}]}
        assert data_get(data, "a.0.b.0.c") == "deep"


class TestDataGetObject:
    """Object attribute fallback."""

    def test_object_attr(self) -> None:
        @dataclass
        class Coord:
            x: int
            y: int

        assert data_get(Coord(x=3, y=7), "x") == 3
        assert data_get(Coord(x=3, y=7), "y") == 7

    def test_nested_object_attr(self) -> None:
        @dataclass
        class Inner:
            value: int

        @dataclass
        class Outer:
            inner: Inner

        obj = Outer(inner=Inner(value=42))
        assert data_get(obj, "inner.value") == 42

    def test_missing_attr_returns_default(self) -> None:
        @dataclass
        class Dummy:
            x: int = 0

        assert data_get(Dummy(), "missing", "fallback") == "fallback"

    def test_dict_then_object(self) -> None:
        @dataclass
        class Point:
            x: int

        data = {"point": Point(x=5)}
        assert data_get(data, "point.x") == 5


class TestDataGetMixed:
    """Mixed dict/list/object combinations."""

    def test_dict_list_dict(self) -> None:
        data = {"teams": [{"name": "Alpha", "lead": "Mo"}]}
        assert data_get(data, "teams.0.lead") == "Mo"

    def test_claims_realm_access_pattern(self) -> None:
        """Real-world JWT claims pattern from Keycloak."""
        claims = {
            "sub": "user-123",
            "realm_access": {"roles": ["admin", "editor"]},
            "groups": ["/org/team-a"],
        }
        assert data_get(claims, "realm_access.roles") == ["admin", "editor"]
        assert data_get(claims, "realm_access.roles.0") == "admin"
        assert data_get(claims, "groups.0") == "/org/team-a"
        assert data_get(claims, "missing.path", []) == []

    def test_deeply_nested_resource_access(self) -> None:
        """Keycloak resource_access pattern."""
        claims = {
            "resource_access": {
                "my-app": {"roles": ["viewer", "editor"]},
            },
        }
        assert data_get(claims, "resource_access.my-app.roles") == ["viewer", "editor"]
        assert data_get(claims, "resource_access.my-app.roles.1") == "editor"

    def test_string_not_treated_as_sequence(self) -> None:
        assert data_get({"name": "Alice"}, "name.0", "nope") == "nope"

    def test_bytes_not_treated_as_sequence(self) -> None:
        assert data_get({"data": b"hello"}, "data.0", "nope") == "nope"


class TestDataGetTypeSafety:
    """Verify the default return type flows through correctly."""

    def test_typed_default_int(self) -> None:
        result: int = data_get({}, "missing", 0)
        assert result == 0
        assert isinstance(result, int)

    def test_typed_default_str(self) -> None:
        result: str = data_get({}, "missing", "")
        assert result == ""
        assert isinstance(result, str)

    def test_typed_default_list(self) -> None:
        result: list[str] = data_get({}, "missing", [])
        assert result == []
        assert isinstance(result, list)

    def test_typed_default_dict(self) -> None:
        result: dict[str, int] = data_get({}, "missing", {})
        assert result == {}
        assert isinstance(result, dict)

    def test_no_default_returns_none(self) -> None:
        result = data_get({}, "missing")
        assert result is None
