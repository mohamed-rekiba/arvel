"""``Collection[T]`` — the single canonical Arvent collection.

every behavioural surface of ``arvel.support.Collection``. The database
layer re-exports the same class; integration wiring is asserted in
``tests/database/test_012_s5_collections_casts_factories.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from arvel.support import Collection


@dataclass(frozen=True)
class Item:
    name: str
    value: int


# list-subclass contract


def test_collection_is_list_subclass() -> None:
    coll = Collection([1, 2, 3])
    assert isinstance(coll, list)
    assert len(coll) == 3
    assert coll[0] == 1


def test_collection_to_array() -> None:
    coll = Collection([1, 2, 3])
    assert coll.to_array() == [1, 2, 3]
    assert list(coll) == [1, 2, 3]


# transformation


def test_filter_and_map_chain() -> None:
    nums = Collection([1, 2, 3, 4, 5])
    evens_doubled = nums.filter(lambda n: n % 2 == 0).map(lambda n: n * 2)
    assert list(evens_doubled) == [4, 8]


def test_reject() -> None:
    nums = Collection([1, 2, 3, 4])
    assert list(nums.reject(lambda n: n % 2 == 0)) == [1, 3]


def test_reduce() -> None:
    nums = Collection([1, 2, 3])
    assert nums.reduce(lambda acc, n: acc + n, 0) == 6


def test_pluck() -> None:
    items = Collection([Item("a", 1), Item("b", 2)])
    assert list(items.pluck("name")) == ["a", "b"]


def test_pluck_raises_on_missing_attr() -> None:
    items = Collection([Item("a", 1)])
    with pytest.raises(AttributeError):
        items.pluck("nonexistent")


def test_unique_without_key() -> None:
    coll = Collection([1, 2, 2, 3, 3, 3])
    assert sorted(coll.unique()) == [1, 2, 3]


def test_unique_with_key() -> None:
    items = Collection([Item("a", 1), Item("b", 1), Item("c", 2)])
    assert len(items.unique("value")) == 2


def test_flatten() -> None:
    coll = Collection([[1, 2], 3, [4, 5]])
    assert list(coll.flatten()) == [1, 2, 3, 4, 5]


def test_sort_by() -> None:
    items = Collection([Item("a", 3), Item("b", 1), Item("c", 2)])
    sorted_asc = items.sort_by("value")
    assert [it.value for it in sorted_asc] == [1, 2, 3]
    sorted_desc = items.sort_by("value", descending=True)
    assert [it.value for it in sorted_desc] == [3, 2, 1]


def test_reverse_returns_new_collection() -> None:
    coll = Collection([1, 2, 3])
    reversed_coll = coll.reverse()
    assert list(reversed_coll) == [3, 2, 1]
    assert list(coll) == [1, 2, 3]  # original unchanged


def test_take_and_skip() -> None:
    coll = Collection([1, 2, 3, 4, 5])
    assert list(coll.take(2)) == [1, 2]
    assert list(coll.take(-2)) == [4, 5]
    assert list(coll.skip(2)) == [3, 4, 5]


def test_chunk() -> None:
    coll = Collection([1, 2, 3, 4, 5])
    chunks = coll.chunk(2)
    assert [list(c) for c in chunks] == [[1, 2], [3, 4], [5]]


def test_chunk_rejects_non_positive_size() -> None:
    with pytest.raises(ValueError, match="chunk size"):
        Collection([1, 2, 3]).chunk(0)


def test_zip() -> None:
    coll = Collection([1, 2, 3])
    zipped = coll.zip(["a", "b", "c"])
    assert list(zipped) == [(1, "a"), (2, "b"), (3, "c")]


# lookup / inspection


def test_first_and_first_where() -> None:
    items = Collection([Item("a", 1), Item("b", 2), Item("c", 2)])
    assert items.first() == Item("a", 1)
    assert items.first_where(value=2) == Item("b", 2)
    assert items.first_where(name="missing") is None


def test_first_with_predicate() -> None:
    coll = Collection([1, 2, 3, 4])
    assert coll.first(lambda n: n > 2) == 3
    assert coll.first(lambda n: n > 10) is None


def test_last() -> None:
    coll = Collection([1, 2, 3])
    assert coll.last() == 3
    assert coll.last(lambda n: n < 3) == 2
    assert Collection[int]().last() is None


def test_contains() -> None:
    coll = Collection([1, 2, 3])
    assert coll.contains(2)
    assert not coll.contains(99)
    assert coll.contains(lambda n: n > 2)


def test_find_returns_matching_value() -> None:
    items = Collection([Item("a", 1), Item("b", 2)])
    assert items.find(Item("b", 2)) == Item("b", 2)
    assert items.find(Item("z", 9)) is None
    assert Collection([1, 2, 3]).find(2) == 2


def test_every_and_some() -> None:
    coll = Collection([2, 4, 6])
    assert coll.every(lambda n: n % 2 == 0)
    assert coll.some(lambda n: n == 4)
    assert not coll.some(lambda n: n == 5)


def test_is_empty_and_is_not_empty() -> None:
    empty: Collection[int] = Collection()
    nonempty = Collection([1])
    assert empty.is_empty()
    assert not empty.is_not_empty()
    assert nonempty.is_not_empty()
    assert not nonempty.is_empty()


# aggregates


def test_sum_and_avg() -> None:
    items = Collection([Item("a", 10), Item("b", 20), Item("c", 30)])
    assert items.sum("value") == 60
    avg = items.avg("value")
    assert isinstance(avg, float)
    assert abs(avg - 20.0) < 1e-9


def test_min_and_max() -> None:
    items = Collection([Item("a", 5), Item("b", 1), Item("c", 9)])
    assert items.min("value") == 1
    assert items.max("value") == 9


def test_aggregates_on_empty_collection_return_none() -> None:
    empty: Collection[Item] = Collection()
    assert empty.sum("value") is None
    assert empty.avg("value") is None
    assert empty.min("value") is None
    assert empty.max("value") is None


def test_count_by() -> None:
    coll = Collection([1, 2, 3, 4])
    grouped = coll.count_by(lambda n: n % 2)
    assert grouped == {1: 2, 0: 2}


# grouping


def test_group_by_attribute() -> None:
    items = Collection([Item("a", 1), Item("b", 2), Item("c", 1)])
    groups = items.group_by("value")
    assert sorted(groups.keys()) == [1, 2]
    assert len(groups[1]) == 2
    assert isinstance(groups[1], Collection)


def test_group_by_callable() -> None:
    coll = Collection([1, 2, 3, 4])
    groups = coll.group_by(lambda n: n % 2)
    assert sorted(groups.keys()) == [0, 1]
    assert sorted(groups[1]) == [1, 3]


def test_key_by() -> None:
    items = Collection([Item("a", 1), Item("b", 2)])
    by_name = items.key_by("name")
    assert by_name["a"].value == 1
    assert by_name["b"].value == 2


# set operations


def test_only_keeps_listed_values() -> None:
    coll = Collection([1, 2, 3, 4])
    assert list(coll.only(2, 4)) == [2, 4]
    assert list(coll.only()) == []


def test_except_drops_listed_values() -> None:
    coll = Collection([1, 2, 3, 4])
    assert list(coll.except_(2, 4)) == [1, 3]
    assert list(coll.except_()) == [1, 2, 3, 4]


def test_merge() -> None:
    a = Collection([1, 2])
    b = [3, 4]
    assert list(a.merge(b)) == [1, 2, 3, 4]


# serialisation


def test_to_json_with_to_dict() -> None:
    import json

    @dataclass(frozen=True)
    class Serial:
        name: str

        def to_dict(self) -> dict[str, str]:
            return {"name": self.name}

    coll = Collection([Serial("a"), Serial("b")])
    parsed = json.loads(coll.to_json())
    assert parsed == [{"name": "a"}, {"name": "b"}]


def test_to_json_with_pydantic_model_dump() -> None:
    import json

    from pydantic import BaseModel

    class Doc(BaseModel):
        title: str

    coll = Collection([Doc(title="x"), Doc(title="y")])
    parsed = json.loads(coll.to_json())
    assert parsed == [{"title": "x"}, {"title": "y"}]


def test_values_returns_new_collection() -> None:
    coll = Collection([1, 2, 3])
    copy = coll.values()
    assert isinstance(copy, Collection)
    assert list(copy) == [1, 2, 3]
    assert copy is not coll


def test_last_with_predicate_no_match_returns_none() -> None:
    assert Collection([1, 2, 3]).last(lambda x: x > 10) is None


def test_intersect_keeps_shared_identities() -> None:
    a, b = object(), object()
    coll = Collection([a, b])
    assert list(coll.intersect([a])) == [a]


def test_diff_drops_shared_identities() -> None:
    a, b = object(), object()
    coll = Collection([a, b])
    assert list(coll.diff([a])) == [b]


def test_to_json_with_to_dict_objects() -> None:
    import json

    class Row:
        def to_dict(self) -> dict[str, int]:
            return {"n": 1}

    assert json.loads(Collection([Row()]).to_json()) == [{"n": 1}]


def test_to_json_with_plain_scalars() -> None:
    import json

    assert json.loads(Collection([1, 2, 3]).to_json()) == [1, 2, 3]
