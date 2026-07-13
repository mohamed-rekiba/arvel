"""C1 — support helpers: Arr, data_get/data_set, flow helpers."""

from __future__ import annotations

import pytest

from arvel.support import Arr, blank, data_get, data_set, filled, pipe, rescue, tap, throw_if, value


def test_data_get_dot_and_wildcard() -> None:
    data = {"user": {"name": "ada", "roles": [{"id": 1}, {"id": 2}]}}
    assert data_get(data, "user.name") == "ada"
    assert data_get(data, "user.missing", "d") == "d"
    assert data_get(data, "user.roles.*.id") == [1, 2]


def test_data_set_creates_nested() -> None:
    target: dict[str, object] = {}
    data_set(target, "a.b.c", 1)
    assert target == {"a": {"b": {"c": 1}}}


def test_arr_helpers() -> None:
    assert Arr.get({"a": {"b": 2}}, "a.b") == 2
    assert Arr.has({"a": 1}, "a") is True
    assert Arr.first([1, 2, 3], lambda x: x > 1) == 2
    assert Arr.last([1, 2, 3]) == 3
    assert Arr.pluck([{"id": 1}, {"id": 2}], "id") == [1, 2]
    assert Arr.flatten([1, [2, [3]]]) == [1, 2, 3]
    assert Arr.only({"a": 1, "b": 2}, ["a"]) == {"a": 1}
    assert Arr.excluding({"a": 1, "b": 2}, ["a"]) == {"b": 2}
    assert Arr.wrap("x") == ["x"]
    assert Arr.wrap(None) == []


def test_tap_pipe_value() -> None:
    seen: list[int] = []
    assert tap(5, lambda v: seen.append(v)) == 5
    assert seen == [5]
    assert pipe(2, lambda x: x + 1, lambda x: x * 10) == 30
    assert value(lambda: 7) == 7
    assert value(7) == 7


def test_blank_filled() -> None:
    assert blank("") is True
    assert blank("  ") is True
    assert blank([]) is True
    assert blank(None) is True
    assert filled("x") is True
    assert filled(0) is True  # 0 is filled (not blank)


def test_throw_if() -> None:
    with pytest.raises(ValueError):
        throw_if(True, ValueError)
    assert throw_if(False, ValueError) is False


def test_rescue_returns_default_on_error() -> None:
    def boom() -> int:
        raise RuntimeError("nope")

    assert rescue(boom, 42) == 42
    assert rescue(lambda: 1) == 1
