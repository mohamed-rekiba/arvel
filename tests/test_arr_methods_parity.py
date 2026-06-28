"""Arr-helper parity (Laravel): common methods that were absent — except_/exists/add/forget,
keys/values/divide, is_assoc/is_list, dot/undot/collapse, where/map_with_keys/prepend,
sort/sort_desc/take/join/random."""

from __future__ import annotations

from arvel.support.helpers import Arr


def test_keys_membership() -> None:
    assert Arr.except_({"a": 1, "b": 2, "c": 3}, ["b"]) == {"a": 1, "c": 3}
    assert Arr.exists({"a": 1}, "a") is True
    assert Arr.exists({"a": 1}, "z") is False
    assert Arr.add({"a": 1}, "b", 2) == {"a": 1, "b": 2}
    assert Arr.add({"a": 1}, "a", 9) == {"a": 1}  # present → unchanged
    assert Arr.add({}, "x.y", 5) == {"x": {"y": 5}}  # dot-aware
    assert Arr.forget({"a": 1, "b": 2}, "b") == {"a": 1}
    assert Arr.forget({"x": {"y": 1, "z": 2}}, "x.y") == {"x": {"z": 2}}  # dot-aware
    assert Arr.keys({"a": 1, "b": 2}) == ["a", "b"]
    assert Arr.values({"a": 1, "b": 2}) == [1, 2]
    assert Arr.divide({"a": 1, "b": 2}) == (["a", "b"], [1, 2])


def test_shape() -> None:
    assert Arr.is_assoc({"a": 1}) is True
    assert Arr.is_assoc([1, 2]) is False
    assert Arr.is_list([1, 2]) is True
    assert Arr.dot({"a": {"b": 1, "c": 2}}) == {"a.b": 1, "a.c": 2}
    assert Arr.undot({"a.b": 1, "a.c": 2}) == {"a": {"b": 1, "c": 2}}
    assert Arr.dot(Arr.undot({"a.b": 1})) == {"a.b": 1}  # round-trips
    assert Arr.collapse([[1, 2], [3], 4]) == [1, 2, 3]  # non-lists ignored


def test_transform_and_order() -> None:
    assert Arr.where([1, 2, 3, 4], lambda x: x % 2 == 0) == [2, 4]
    assert Arr.where({"a": 1, "b": 2}, lambda v: v > 1) == {"b": 2}
    assert Arr.map_with_keys([("a", 1), ("b", 2)], lambda x: x) == {"a": 1, "b": 2}
    assert Arr.prepend([2, 3], 1) == [1, 2, 3]
    assert Arr.sort([3, 1, 2]) == [1, 2, 3]
    assert Arr.sort_desc([1, 3, 2]) == [3, 2, 1]
    assert Arr.take([1, 2, 3, 4], 2) == [1, 2]
    assert Arr.take([1, 2, 3, 4], -2) == [3, 4]
    assert Arr.join(["a", "b", "c"], ", ") == "a, b, c"
    assert Arr.join(["a", "b", "c"], ", ", " and ") == "a, b and c"


def test_random() -> None:
    assert Arr.random([1, 2, 3]) in {1, 2, 3}
    chosen = Arr.random([1, 2, 3, 4], 2)
    assert len(chosen) == 2 and len(set(chosen)) == 2
    assert all(x in {1, 2, 3, 4} for x in chosen)
