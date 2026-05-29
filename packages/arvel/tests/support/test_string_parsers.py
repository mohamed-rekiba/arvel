"""Str coercion methods and migration name extractors."""

from __future__ import annotations

import pytest
from arvel.database.migrations import (
    extract_extension_name,
    extract_table_name,
    extract_view_name,
)
from arvel.support.str import Str


def test_extract_names_from_migration_names() -> None:
    assert extract_table_name("CreateCategoryTable") == "categories"
    assert extract_table_name("AddUserTable") == "users"
    assert extract_extension_name("install_pg_trgm_extension") == "pg_trgm"
    assert extract_view_name("CreateActiveUsersView") == "active_users"


def test_to_bool_accepts_true_and_false_values() -> None:
    assert Str.to_bool(" yes ") is True
    assert Str.to_bool("off") is False


@pytest.mark.parametrize("value", [None, "", "maybe"])
def test_to_bool_rejects_invalid_values(value: object) -> None:
    with pytest.raises(ValueError):
        Str.to_bool(value)


def test_to_number_parsers() -> None:
    assert Str.to_int("42") == 42
    assert Str.to_float("3.5") == 3.5

    with pytest.raises(ValueError, match="Invalid integer"):
        Str.to_int("not-int")
    with pytest.raises(ValueError, match="Invalid float"):
        Str.to_float("not-float")


def test_to_list_options() -> None:
    assert Str.to_list("a, b,,c", remove_empty=True) == ["a", "b", "c"]
    assert Str.to_list("a| b ", separator="|", strip_items=False) == ["a", " b"]


def test_to_dict_parses_and_rejects_bad_pairs() -> None:
    assert Str.to_dict("a=1,b=2") == {"a": "1", "b": "2"}
    assert Str.to_dict("a:1;b:2", item_separator=";", key_value_separator=":") == {
        "a": "1",
        "b": "2",
    }

    with pytest.raises(ValueError, match="Invalid key-value pair"):
        Str.to_dict("a=1,b")
    with pytest.raises(ValueError, match="Value cannot be empty"):
        Str.to_dict("a=")
