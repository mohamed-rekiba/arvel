"""Arr — pull / has_any / where_not_null (Laravel Arr::pull/hasAny/whereNotNull parity). pull reads a
dot-key then removes it in place; has_any tests whether ANY key is present; where_not_null drops None
values preserving keys/order."""

from __future__ import annotations

from arvel.support.helpers import Arr


def test_pull_returns_and_removes() -> None:
    data = {"a": 1, "b": 2}
    assert Arr.pull(data, "a") == 1
    assert data == {"b": 2}  # removed in place
    assert Arr.pull(data, "missing", "default") == "default"  # default on absent


def test_pull_nested_dot_key() -> None:
    data = {"user": {"name": "Ada", "secret": "x"}}
    assert Arr.pull(data, "user.secret") == "x"
    assert data == {"user": {"name": "Ada"}}  # nested key removed


def test_has_any() -> None:
    data = {"a": 1, "b": 2}
    assert Arr.has_any(data, ["x", "b"]) is True  # at least one present
    assert Arr.has_any(data, ["x", "y"]) is False
    assert Arr.has_any(data, "a") is True  # single key
    assert Arr.has_any(data, "user.name") is False


def test_where_not_null() -> None:
    assert Arr.where_not_null({"a": 1, "b": None, "c": 3}) == {"a": 1, "c": 3}
    assert Arr.where_not_null([1, None, 2, None]) == [1, 2]  # list form preserves order
