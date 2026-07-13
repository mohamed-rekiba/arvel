"""Coverage — support helpers (Arr, data_get/set, flow helpers)."""

from __future__ import annotations

import pytest

from arvel.support.helpers import (
    Arr,
    blank,
    data_get,
    data_set,
    filled,
    pipe,
    rescue,
    retry,
    tap,
    throw_if,
    value,
)


class Obj:
    def __init__(self) -> None:
        self.name = "x"


def test_value() -> None:
    assert value(5) == 5
    assert value(lambda: 7) == 7


def test_data_get_paths() -> None:
    data = {"user": {"name": "ada", "tags": ["a", "b"]}}
    assert data_get(data, "user.name") == "ada"
    assert data_get(data, "user.tags.1") == "b"
    assert data_get(data, "user.missing", "default") == "default"
    assert data_get(data, None) is data
    assert data_get(Obj(), "name") == "x"  # attribute access
    assert data_get({"k": "v"}, "k.x.y", "d") == "d"  # descend past a non-container


def test_data_get_wildcard() -> None:
    data = {"items": [{"id": 1}, {"id": 2}]}
    assert data_get(data, "items.*.id") == [1, 2]
    assert data_get({"items": "nope"}, "items.*.id", "d") == "d"


def test_data_set() -> None:
    target: dict[str, object] = {}
    data_set(target, "a.b.c", 1)
    assert target == {"a": {"b": {"c": 1}}}
    data_set(target, "a.b.c", 2, overwrite=False)
    assert target["a"]["b"]["c"] == 1  # type: ignore[index]


def test_tap_pipe() -> None:
    seen = []
    assert tap(5, lambda x: seen.append(x)) == 5
    assert seen == [5]
    assert tap(9) == 9
    assert pipe(2, lambda x: x + 1, lambda x: x * 10) == 30


def test_blank_filled() -> None:
    assert blank(None) and blank("  ") and blank([]) and blank({})
    assert not blank("x") and not blank([1])
    assert filled("x") and not filled("")
    assert not blank(0)  # 0 is filled


def test_throw_if() -> None:
    assert throw_if(False, ValueError) is False
    with pytest.raises(ValueError):
        throw_if(True, ValueError)
    with pytest.raises(RuntimeError, match="boom"):
        throw_if(True, RuntimeError("boom"))


def test_rescue() -> None:
    assert rescue(lambda: 1 / 0, "fallback") == "fallback"
    assert rescue(lambda: 42) == 42


def test_retry() -> None:
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError
        return "ok"

    assert retry(5, flaky) == "ok"
    assert calls["n"] == 3
    with pytest.raises(ZeroDivisionError):
        retry(2, lambda: 1 / 0)


def test_arr() -> None:
    assert Arr.get({"a": {"b": 1}}, "a.b") == 1
    assert Arr.has({"a": 1}, "a")
    assert not Arr.has({"a": 1}, "z")
    assert Arr.first([1, 2, 3], lambda x: x > 1) == 2
    assert Arr.first([], default="d") == "d"
    assert Arr.last([1, 2, 3], lambda x: x < 3) == 2
    assert Arr.last([], default=lambda: "dl") == "dl"
    assert Arr.pluck([{"id": 1}, {"id": 2}], "id") == [1, 2]
    assert Arr.flatten([1, [2, [3]]]) == [1, 2, 3]
