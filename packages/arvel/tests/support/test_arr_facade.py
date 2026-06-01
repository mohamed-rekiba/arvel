"""arvel.support.Arr — Laravel-parity array/dict facade."""

from __future__ import annotations

import pytest
from arvel.support import Arr


class TestArrFirst:
    def test_no_predicate_returns_first(self) -> None:
        assert Arr.first([1, 2, 3]) == 1

    def test_predicate(self) -> None:
        assert Arr.first([1, 2, 3], lambda x: x > 1) == 2

    def test_default_when_empty(self) -> None:
        assert Arr.first([], default="missing") == "missing"

    def test_default_when_no_match(self) -> None:
        assert Arr.first([1, 2, 3], lambda x: x > 10, default=-1) == -1


class TestArrLast:
    def test_no_predicate_returns_last(self) -> None:
        assert Arr.last([1, 2, 3]) == 3

    def test_predicate(self) -> None:
        assert Arr.last([1, 2, 3, 4], lambda x: x < 4) == 3

    def test_default_when_empty(self) -> None:
        assert Arr.last([], default="missing") == "missing"


class TestArrFlatten:
    def test_default_full_depth(self) -> None:
        assert Arr.flatten([[1, [2, 3]], 4]) == [1, 2, 3, 4]

    def test_depth_one(self) -> None:
        assert Arr.flatten([[1, [2, 3]], 4], depth=1) == [1, [2, 3], 4]

    def test_already_flat(self) -> None:
        assert Arr.flatten([1, 2, 3]) == [1, 2, 3]


class TestArrOnly:
    def test_only_picks_keys(self) -> None:
        assert Arr.only({"a": 1, "b": 2, "c": 3}, ["a", "c"]) == {"a": 1, "c": 3}

    def test_missing_keys_omitted(self) -> None:
        assert Arr.only({"a": 1}, ["a", "b"]) == {"a": 1}


class TestArrExcept:
    def test_except_drops_keys(self) -> None:
        assert Arr.except_({"a": 1, "b": 2}, ["b"]) == {"a": 1}

    def test_drop_unknown_keys_is_noop(self) -> None:
        assert Arr.except_({"a": 1}, ["b"]) == {"a": 1}


class TestArrDotUndot:
    def test_dot_simple(self) -> None:
        assert Arr.dot({"a": {"b": 1}}) == {"a.b": 1}

    def test_dot_deep(self) -> None:
        assert Arr.dot({"a": {"b": {"c": 1, "d": 2}}}) == {"a.b.c": 1, "a.b.d": 2}

    def test_dot_preserves_lists(self) -> None:
        assert Arr.dot({"a": [1, 2, 3]}) == {"a": [1, 2, 3]}

    def test_undot_simple(self) -> None:
        assert Arr.undot({"a.b": 1}) == {"a": {"b": 1}}

    def test_undot_overlap(self) -> None:
        assert Arr.undot({"a.b": 1, "a.c": 2}) == {"a": {"b": 1, "c": 2}}

    def test_dot_undot_roundtrip(self) -> None:
        original: dict[str, object] = {"users": {"alice": {"age": 30, "role": "admin"}}}
        assert Arr.undot(Arr.dot(original)) == original


class TestArrGetSet:
    def test_get_dot_notation(self) -> None:
        d = {"a": {"b": {"c": 42}}}
        assert Arr.get(d, "a.b.c") == 42

    def test_get_top_level(self) -> None:
        assert Arr.get({"a": 1}, "a") == 1

    def test_get_default_on_missing(self) -> None:
        assert Arr.get({"a": 1}, "b", default="missing") == "missing"

    def test_get_default_on_partial(self) -> None:
        assert Arr.get({"a": {}}, "a.b.c", default=None) is None

    def test_set_dot_notation_creates_path(self) -> None:
        d: dict[str, object] = {}
        Arr.set(d, "a.b.c", 42)
        assert d == {"a": {"b": {"c": 42}}}

    def test_set_top_level(self) -> None:
        d: dict[str, object] = {}
        Arr.set(d, "key", "value")
        assert d == {"key": "value"}

    def test_set_overwrites_non_dict(self) -> None:
        d: dict[str, object] = {"a": 1}
        Arr.set(d, "a.b", 2)
        assert d == {"a": {"b": 2}}


class TestArrHas:
    def test_has_simple(self) -> None:
        assert Arr.has({"a": 1}, "a") is True
        assert Arr.has({"a": 1}, "b") is False

    def test_has_nested(self) -> None:
        d = {"a": {"b": {"c": 1}}}
        assert Arr.has(d, "a.b.c") is True
        assert Arr.has(d, "a.b.d") is False

    def test_has_none_value_counted_as_present(self) -> None:
        assert Arr.has({"a": None}, "a") is True


class TestArrPluck:
    def test_pluck_dicts(self) -> None:
        items: list[dict[str, object]] = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
        assert Arr.pluck(items, "name") == ["a", "b"]

    def test_pluck_objects(self) -> None:
        class Box:
            def __init__(self, x: int) -> None:
                self.x = x

        assert Arr.pluck([Box(1), Box(2)], "x") == [1, 2]

    def test_pluck_with_key(self) -> None:
        items: list[dict[str, object]] = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
        assert Arr.pluck(items, "name", key="id") == {1: "a", 2: "b"}


class TestArrWrap:
    def test_wrap_none_to_empty_list(self) -> None:
        assert Arr.wrap(None) == []

    def test_wrap_scalar(self) -> None:
        assert Arr.wrap("x") == ["x"]

    def test_wrap_passes_list(self) -> None:
        assert Arr.wrap([1, 2]) == [1, 2]

    def test_wrap_tuple_normalizes_to_list(self) -> None:
        assert Arr.wrap((1, 2)) == [1, 2]


class TestArrPrependAppend:
    def test_prepend(self) -> None:
        assert Arr.prepend([2, 3], 1) == [1, 2, 3]
        # source is not mutated
        src = [2, 3]
        Arr.prepend(src, 1)
        assert src == [2, 3]


class TestArrWhere:
    def test_where_predicate(self) -> None:
        assert Arr.where([1, 2, 3, 4], lambda x: x % 2 == 0) == [2, 4]


class TestArrShuffleSafety:
    """The Laravel Arr.shuffle exists; check it returns the same elements."""

    def test_shuffle_returns_same_elements(self) -> None:
        src = [1, 2, 3, 4, 5]
        shuffled = Arr.shuffle(src)
        assert sorted(shuffled) == src
        # original not mutated
        assert src == [1, 2, 3, 4, 5]


class TestArrDivide:
    def test_divide_separates_keys_and_values(self) -> None:
        keys, values = Arr.divide({"a": 1, "b": 2})
        assert keys == ["a", "b"]
        assert values == [1, 2]


class TestArrInteropWithCollection:
    """Arr methods accept any sequence and emit plain lists."""

    def test_first_with_tuple(self) -> None:
        assert Arr.first((10, 20, 30)) == 10

    def test_flatten_with_generator(self) -> None:
        gen = (x for x in [[1, 2], [3]])
        assert Arr.flatten(gen) == [1, 2, 3]


class TestArrInputValidation:
    def test_get_on_non_dict_returns_default(self) -> None:
        # Mid-path traversal hits a non-dict value
        d = {"a": "string"}
        assert Arr.get(d, "a.b", default="missing") == "missing"

    def test_only_with_empty_keys_returns_empty_dict(self) -> None:
        assert Arr.only({"a": 1}, []) == {}

    def test_pluck_returns_empty_list_for_empty_input(self) -> None:
        assert Arr.pluck([], "name") == []


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        ([], None),
        ([0], 0),
        ([False], False),
        (["", "x"], ""),
    ],
)
def test_first_falsy_first_item_is_returned(items: list[object], expected: object) -> None:
    """Falsy items must not be silently skipped without a predicate."""
    assert Arr.first(items) == expected
