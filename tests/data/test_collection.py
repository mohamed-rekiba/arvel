"""Tests for ArvelCollection — fluent collection wrapping query results."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from arvel.data.collection import ArvelCollection

# ──── Helpers ────


@dataclass
class Item:
    name: str
    age: int
    role: str = "user"


def _items() -> ArvelCollection[Item]:
    return ArvelCollection(
        [
            Item("Alice", 30, "admin"),
            Item("Bob", 25, "user"),
            Item("Charlie", 35, "admin"),
            Item("Diana", 28, "user"),
            Item("Eve", 25, "user"),
        ]
    )


# ──── Sequence behavior ────


class TestSequenceBehavior:
    def test_is_a_list(self):
        c = ArvelCollection([1, 2, 3])
        assert isinstance(c, list)

    def test_len(self):
        assert len(ArvelCollection([1, 2, 3])) == 3

    def test_iteration(self):
        items = list(ArvelCollection([1, 2, 3]))
        assert items == [1, 2, 3]

    def test_indexing(self):
        c = ArvelCollection(["a", "b", "c"])
        assert c[0] == "a"
        assert c[-1] == "c"

    def test_truthiness_empty(self):
        assert not ArvelCollection([])

    def test_truthiness_nonempty(self):
        assert ArvelCollection([1])

    def test_repr(self):
        c = ArvelCollection([1, 2])
        assert repr(c) == "ArvelCollection([1, 2])"


# ──── Element access ────


class TestElementAccess:
    def test_first_returns_first_item(self):
        c = _items()
        first = c.first()
        assert first is not None
        assert first.name == "Alice"

    def test_first_empty_returns_default(self):
        c: ArvelCollection[Item] = ArvelCollection()
        assert c.first() is None
        assert c.first(Item("X", 0)) == Item("X", 0)

    def test_last_returns_last_item(self):
        c = _items()
        last = c.last()
        assert last is not None
        assert last.name == "Eve"

    def test_last_empty_returns_default(self):
        c: ArvelCollection[Item] = ArvelCollection()
        assert c.last() is None


# ──── Transformation ────


class TestTransformation:
    def test_map(self):
        c = ArvelCollection([1, 2, 3])
        result = c.map(lambda x: x * 2)
        assert isinstance(result, ArvelCollection)
        assert result.to_list() == [2, 4, 6]

    def test_flat_map(self):
        c = ArvelCollection([1, 2, 3])
        result = c.flat_map(lambda x: [x, x * 10])
        assert result.to_list() == [1, 10, 2, 20, 3, 30]

    def test_filter_with_function(self):
        c = _items()
        admins = c.filter(lambda x: x.role == "admin")
        assert isinstance(admins, ArvelCollection)
        assert len(admins) == 2

    def test_filter_truthy_values(self):
        c = ArvelCollection([0, 1, None, "hello", "", False])
        result = c.filter()
        assert result.to_list() == [1, "hello"]

    def test_reject(self):
        c = _items()
        non_admins = c.reject(lambda x: x.role == "admin")
        assert len(non_admins) == 3

    def test_each_returns_self(self):
        captured: list[str] = []
        c = _items()
        returned = c.each(lambda x: captured.append(x.name))
        assert returned is c
        assert len(captured) == 5


# ──── Extraction ────


class TestExtraction:
    def test_pluck_attribute(self):
        c = _items()
        names = c.pluck("name")
        assert names.to_list() == ["Alice", "Bob", "Charlie", "Diana", "Eve"]

    def test_pluck_dict_key(self):
        c = ArvelCollection([{"name": "a"}, {"name": "b"}])
        assert c.pluck("name").to_list() == ["a", "b"]

    def test_pluck_missing_key(self):
        c = _items()
        result = c.pluck("nonexistent")
        assert result.to_list() == [None, None, None, None, None]


# ──── Filtering / searching ────


class TestFiltering:
    def test_where_attribute(self):
        c = _items()
        admins = c.where("role", "admin")
        assert len(admins) == 2
        assert all(x.role == "admin" for x in admins)

    def test_where_dict(self):
        c = ArvelCollection([{"role": "admin"}, {"role": "user"}, {"role": "admin"}])
        result = c.where("role", "admin")
        assert len(result) == 2

    def test_where_in(self):
        c = _items()
        result = c.where_in("name", ["Alice", "Eve"])
        assert len(result) == 2

    def test_first_where(self):
        c = _items()
        found = c.first_where("name", "Charlie")
        assert found is not None
        assert found.age == 35

    def test_first_where_not_found(self):
        c = _items()
        assert c.first_where("name", "Zack") is None

    def test_contains_with_callable(self):
        c = _items()
        assert c.contains(lambda x: x.name == "Alice")
        assert not c.contains(lambda x: x.name == "Zack")

    def test_contains_with_value(self):
        c = ArvelCollection([1, 2, 3])
        assert c.contains(2)
        assert not c.contains(99)


# ──── Grouping / chunking ────


class TestGrouping:
    def test_group_by_attribute(self):
        c = _items()
        groups = c.group_by("role")
        assert set(groups.keys()) == {"admin", "user"}
        assert len(groups["admin"]) == 2
        assert len(groups["user"]) == 3
        assert isinstance(groups["admin"], ArvelCollection)

    def test_group_by_callable(self):
        c = ArvelCollection([1, 2, 3, 4, 5])
        groups = c.group_by(lambda x: "even" if x % 2 == 0 else "odd")
        assert len(groups["odd"]) == 3
        assert len(groups["even"]) == 2

    def test_chunk(self):
        c = ArvelCollection([1, 2, 3, 4, 5])
        chunks = c.chunk(2)
        assert isinstance(chunks, ArvelCollection)
        assert len(chunks) == 3
        assert chunks[0].to_list() == [1, 2]
        assert chunks[1].to_list() == [3, 4]
        assert chunks[2].to_list() == [5]

    def test_chunk_exact_division(self):
        c = ArvelCollection([1, 2, 3, 4])
        chunks = c.chunk(2)
        assert len(chunks) == 2

    def test_chunk_size_zero_raises(self):
        c = ArvelCollection([1])
        with pytest.raises(ValueError, match="chunk size"):
            c.chunk(0)

    def test_chunk_empty(self):
        c: ArvelCollection[int] = ArvelCollection()
        assert c.chunk(5).to_list() == []


# ──── Ordering / uniqueness ────


class TestOrdering:
    def test_sort_by_attribute(self):
        c = _items()
        sorted_c = c.sort_by("age")
        assert sorted_c.pluck("age").to_list() == [25, 25, 28, 30, 35]

    def test_sort_by_descending(self):
        c = _items()
        sorted_c = c.sort_by("age", descending=True)
        assert sorted_c.pluck("age").to_list() == [35, 30, 28, 25, 25]

    def test_sort_by_callable(self):
        c = ArvelCollection([3, 1, 2])
        assert c.sort_by(lambda x: x).to_list() == [1, 2, 3]

    def test_unique_primitives(self):
        c = ArvelCollection([1, 2, 2, 3, 3, 3])
        result = c.unique()
        assert result.to_list() == [1, 2, 3]

    def test_unique_by_key(self):
        c = _items()
        result = c.unique("role")
        assert len(result) == 2

    def test_unique_by_callable(self):
        c = _items()
        result = c.unique(lambda x: x.age)
        assert len(result) == 4  # 30, 25, 35, 28 (one 25 deduped)

    def test_reverse(self):
        c = ArvelCollection([1, 2, 3])
        result = c.reverse()
        assert isinstance(result, ArvelCollection)
        assert result.to_list() == [3, 2, 1]


# ──── Aggregation ────


class TestAggregation:
    def test_count(self):
        assert _items().count() == 5

    def test_sum_primitives(self):
        c = ArvelCollection([1, 2, 3])
        assert c.sum() == 6

    def test_sum_by_key(self):
        c = _items()
        assert c.sum("age") == 143

    def test_sum_by_callable(self):
        c = _items()
        assert c.sum(lambda x: x.age) == 143

    def test_avg(self):
        c = ArvelCollection([10, 20, 30])
        assert c.avg() == pytest.approx(20.0)

    def test_avg_empty(self):
        c: ArvelCollection[int] = ArvelCollection()
        assert c.avg() == 0.0

    def test_avg_by_key(self):
        c = _items()
        assert c.avg("age") == pytest.approx(28.6)

    def test_min_primitives(self):
        c = ArvelCollection([3, 1, 2])
        assert c.min() == 1

    def test_min_empty(self):
        c: ArvelCollection[int] = ArvelCollection()
        assert c.min() is None

    def test_min_by_key(self):
        c = _items()
        assert c.min("age") == 25

    def test_max_primitives(self):
        c = ArvelCollection([3, 1, 2])
        assert c.max() == 3

    def test_max_by_key(self):
        c = _items()
        assert c.max("age") == 35


# ──── Conversion ────


class TestConversion:
    def test_to_list(self):
        c = ArvelCollection([1, 2, 3])
        result = c.to_list()
        assert isinstance(result, list)
        assert not isinstance(result, ArvelCollection)

    def test_to_dict(self):
        c = _items()
        d = c.to_dict("name")
        assert "Alice" in d
        assert d["Alice"].age == 30

    def test_is_empty(self):
        assert ArvelCollection().is_empty()
        assert not _items().is_empty()

    def test_is_not_empty(self):
        assert _items().is_not_empty()
        assert not ArvelCollection().is_not_empty()

    def test_values(self):
        c = _items()
        v = c.values()
        assert isinstance(v, ArvelCollection)
        assert len(v) == len(c)


# ──── Slicing ────


class TestSlicing:
    def test_take_positive(self):
        assert ArvelCollection([1, 2, 3, 4, 5]).take(3).to_list() == [1, 2, 3]

    def test_take_negative(self):
        assert ArvelCollection([1, 2, 3, 4, 5]).take(-2).to_list() == [4, 5]

    def test_skip(self):
        assert ArvelCollection([1, 2, 3, 4, 5]).skip(2).to_list() == [3, 4, 5]

    def test_slice_with_length(self):
        assert ArvelCollection([1, 2, 3, 4, 5]).slice(1, 3).to_list() == [2, 3, 4]

    def test_slice_without_length(self):
        assert ArvelCollection([1, 2, 3, 4, 5]).slice(2).to_list() == [3, 4, 5]

    def test_nth(self):
        assert ArvelCollection([1, 2, 3, 4, 5, 6]).nth(2).to_list() == [1, 3, 5]

    def test_nth_with_offset(self):
        assert ArvelCollection([1, 2, 3, 4, 5, 6]).nth(2, offset=1).to_list() == [2, 4, 6]

    def test_for_page(self):
        c = ArvelCollection(range(1, 11))
        assert c.for_page(1, 3).to_list() == [1, 2, 3]
        assert c.for_page(2, 3).to_list() == [4, 5, 6]
        assert c.for_page(4, 3).to_list() == [10]

    def test_take_while(self):
        c = ArvelCollection([1, 2, 3, 4, 1, 2])
        assert c.take_while(lambda x: x < 4).to_list() == [1, 2, 3]

    def test_take_until(self):
        c = ArvelCollection([1, 2, 3, 4, 5])
        assert c.take_until(lambda x: x == 3).to_list() == [1, 2]

    def test_skip_while(self):
        c = ArvelCollection([1, 2, 3, 4, 1])
        assert c.skip_while(lambda x: x < 3).to_list() == [3, 4, 1]

    def test_skip_until(self):
        c = ArvelCollection([1, 2, 3, 4, 5])
        assert c.skip_until(lambda x: x == 3).to_list() == [3, 4, 5]


# ──── Set operations ────


class TestSetOperations:
    def test_merge(self):
        a = ArvelCollection([1, 2])
        b = [3, 4]
        assert a.merge(b).to_list() == [1, 2, 3, 4]

    def test_concat(self):
        assert ArvelCollection([1]).concat([2, 3]).to_list() == [1, 2, 3]

    def test_diff(self):
        assert ArvelCollection([1, 2, 3, 4]).diff([2, 4]).to_list() == [1, 3]

    def test_intersect(self):
        assert ArvelCollection([1, 2, 3, 4]).intersect([2, 4, 6]).to_list() == [2, 4]

    def test_zip(self):
        result = ArvelCollection([1, 2, 3]).zip(["a", "b", "c"])
        assert result.to_list() == [(1, "a"), (2, "b"), (3, "c")]


# ──── Partitioning / splitting ────


class TestPartitioning:
    def test_partition(self):
        evens, odds = ArvelCollection([1, 2, 3, 4, 5]).partition(lambda x: x % 2 == 0)
        assert evens.to_list() == [2, 4]
        assert odds.to_list() == [1, 3, 5]

    def test_split(self):
        groups = ArvelCollection([1, 2, 3, 4, 5]).split(3)
        assert len(groups) == 3
        assert groups[0].to_list() == [1, 2]
        assert groups[1].to_list() == [3, 4]
        assert groups[2].to_list() == [5]

    def test_split_raises_on_zero(self):
        with pytest.raises(ValueError, match="split count"):
            ArvelCollection([1]).split(0)

    def test_sliding(self):
        result = ArvelCollection([1, 2, 3, 4, 5]).sliding(3)
        assert len(result) == 3
        assert result[0].to_list() == [1, 2, 3]
        assert result[1].to_list() == [2, 3, 4]
        assert result[2].to_list() == [3, 4, 5]

    def test_sliding_with_step(self):
        result = ArvelCollection([1, 2, 3, 4, 5]).sliding(2, step=2)
        assert len(result) == 2
        assert result[0].to_list() == [1, 2]
        assert result[1].to_list() == [3, 4]


# ──── Flattening ────


class TestFlattening:
    def test_flatten(self):
        c = ArvelCollection([[1, 2], [3, [4, 5]]])
        assert c.flatten().to_list() == [1, 2, 3, 4, 5]

    def test_flatten_depth_1(self):
        c = ArvelCollection([[1, 2], [3, [4, 5]]])
        assert c.flatten(depth=1).to_list() == [1, 2, 3, [4, 5]]

    def test_collapse(self):
        c = ArvelCollection([[1, 2], [3, 4]])
        assert c.collapse().to_list() == [1, 2, 3, 4]


# ──── Conditional flow ────


class TestConditionalFlow:
    def test_pipe(self):
        result = ArvelCollection([1, 2, 3]).pipe(lambda c: c.sum())
        assert result == 6

    def test_tap(self):
        side_effects: list[int] = []
        c = ArvelCollection([1, 2, 3]).tap(lambda c: side_effects.append(c.count()))
        assert side_effects == [3]
        assert c.to_list() == [1, 2, 3]

    def test_when_true(self):
        result = ArvelCollection([1, 2, 3]).when(True, lambda c: c.take(2))
        assert result.to_list() == [1, 2]

    def test_when_false(self):
        result = ArvelCollection([1, 2, 3]).when(False, lambda c: c.take(2))
        assert result.to_list() == [1, 2, 3]

    def test_when_false_with_default(self):
        result = ArvelCollection([1, 2, 3]).when(
            False, lambda c: c.take(1), default=lambda c: c.take(2)
        )
        assert result.to_list() == [1, 2]

    def test_when_true_ignores_default(self):
        result = ArvelCollection([1, 2, 3]).when(
            True, lambda c: c.take(1), default=lambda c: c.take(2)
        )
        assert result.to_list() == [1]

    def test_unless_true(self):
        result = ArvelCollection([1, 2, 3]).unless(True, lambda c: c.take(2))
        assert result.to_list() == [1, 2, 3]

    def test_unless_false(self):
        result = ArvelCollection([1, 2, 3]).unless(False, lambda c: c.take(2))
        assert result.to_list() == [1, 2]

    def test_unless_true_with_default(self):
        result = ArvelCollection([1, 2, 3]).unless(
            True, lambda c: c.take(1), default=lambda c: c.take(2)
        )
        assert result.to_list() == [1, 2]

    def test_unless_false_ignores_default(self):
        result = ArvelCollection([1, 2, 3]).unless(
            False, lambda c: c.take(1), default=lambda c: c.take(2)
        )
        assert result.to_list() == [1]


# ──── Reduction / folding ────


class TestReduction:
    def test_reduce(self):
        result = ArvelCollection([1, 2, 3, 4]).reduce(lambda acc, x: acc + x, 0)
        assert result == 10

    def test_every_true(self):
        assert ArvelCollection([2, 4, 6]).every(lambda x: x % 2 == 0)

    def test_every_false(self):
        assert not ArvelCollection([2, 3, 6]).every(lambda x: x % 2 == 0)

    def test_some_true(self):
        assert ArvelCollection([1, 2, 3]).some(lambda x: x == 2)

    def test_some_false(self):
        assert not ArvelCollection([1, 3, 5]).some(lambda x: x == 2)


# ──── Searching ────


class TestSearching:
    def test_search_value(self):
        assert ArvelCollection([10, 20, 30]).search(20) == 1

    def test_search_not_found(self):
        assert ArvelCollection([10, 20, 30]).search(99) is None

    def test_search_callable(self):
        assert ArvelCollection([10, 20, 30]).search(lambda x: x > 15) == 1

    def test_sole_single(self):
        assert ArvelCollection([42]).sole() == 42

    def test_sole_multiple_raises(self):
        with pytest.raises(ValueError, match="Expected exactly 1"):
            ArvelCollection([1, 2]).sole()

    def test_sole_with_predicate(self):
        result = ArvelCollection([1, 2, 3]).sole(lambda x: x == 2)
        assert result == 2

    def test_sole_no_match_raises(self):
        with pytest.raises(ValueError, match="Expected exactly 1"):
            ArvelCollection([1, 2, 3]).sole(lambda x: x > 5)


# ──── String ────


class TestImplode:
    def test_implode_values(self):
        assert ArvelCollection(["a", "b", "c"]).implode(", ") == "a, b, c"

    def test_implode_with_key(self):
        items = ArvelCollection(_items())
        assert "Alice" in items.implode(", ", key="name")


# ──── Randomness ────


class TestRandomness:
    def test_random_single(self):
        c = ArvelCollection([1, 2, 3, 4, 5])
        assert c.random() in c

    def test_random_multiple(self):
        c = ArvelCollection([1, 2, 3, 4, 5])
        result = c.random(3)
        assert isinstance(result, ArvelCollection)
        assert len(result) == 3

    def test_random_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            ArvelCollection().random()

    def test_shuffle(self):
        c = ArvelCollection([1, 2, 3, 4, 5])
        shuffled = c.shuffle()
        assert isinstance(shuffled, ArvelCollection)
        assert sorted(shuffled) == sorted(c)


# ──── Extended aggregation ────


class TestExtendedAggregation:
    def test_median(self):
        assert ArvelCollection([1, 3, 5]).median() == 3.0

    def test_median_with_key(self):
        assert _items().median("age") == 28.0

    def test_median_empty(self):
        assert ArvelCollection().median() == 0.0

    def test_mode(self):
        result = ArvelCollection([1, 2, 2, 3, 3]).mode()
        assert set(result) == {2, 3}

    def test_mode_single(self):
        result = ArvelCollection([1, 2, 2, 3]).mode()
        assert result.to_list() == [2]

    def test_count_by(self):
        result = ArvelCollection([1, 1, 2, 3, 3, 3]).count_by()
        assert result == {1: 2, 2: 1, 3: 3}

    def test_count_by_key(self):
        result = _items().count_by("role")
        assert result == {"admin": 2, "user": 3}

    def test_duplicates(self):
        result = ArvelCollection([1, 2, 2, 3, 3, 4]).duplicates()
        assert set(result) == {2, 3}

    def test_duplicates_with_key(self):
        result = _items().duplicates("role")
        assert len(result) == 2


# ──── Mutation ────


class TestMutation:
    def test_prepend(self):
        assert ArvelCollection([2, 3]).prepend(1).to_list() == [1, 2, 3]

    def test_push(self):
        assert ArvelCollection([1, 2]).push(3, 4).to_list() == [1, 2, 3, 4]

    def test_pop_item(self):
        item, rest = ArvelCollection([1, 2, 3]).pop_item()
        assert item == 3
        assert rest.to_list() == [1, 2]

    def test_pop_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            ArvelCollection().pop_item()

    def test_shift(self):
        item, rest = ArvelCollection([1, 2, 3]).shift()
        assert item == 1
        assert rest.to_list() == [2, 3]

    def test_shift_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            ArvelCollection().shift()


# ──── collect() factory ────


class TestCollect:
    def test_collect_from_list(self):
        from arvel.data.collection import collect

        c = collect([1, 2, 3])
        assert isinstance(c, ArvelCollection)
        assert c.to_list() == [1, 2, 3]

    def test_collect_from_generator(self):
        from arvel.data.collection import collect

        c = collect(x * 2 for x in range(3))
        assert c.to_list() == [0, 2, 4]

    def test_collect_none(self):
        from arvel.data.collection import collect

        c = collect()
        assert c.is_empty()


# ──── Niche utilities ────


class TestNicheUtilities:
    def test_ensure_all_match(self):
        c = ArvelCollection([1, 2, 3])
        assert c.ensure(int) is c

    def test_ensure_mixed_types_raises(self):
        c = ArvelCollection([1, "two", 3])
        with pytest.raises(TypeError, match="Expected int, got str"):
            c.ensure(int)

    def test_ensure_multiple_types(self):
        c = ArvelCollection([1, "two", 3.0])
        assert c.ensure(int, str, float) is c

    def test_percentage(self):
        c = ArvelCollection([1, 2, 3, 4, 5])
        assert c.percentage(lambda x: x > 3) == 40.0

    def test_percentage_empty(self):
        assert ArvelCollection().percentage(lambda x: True) == 0.0

    def test_percentage_all_match(self):
        c = ArvelCollection([2, 4, 6])
        assert c.percentage(lambda x: x % 2 == 0) == 100.0

    def test_percentage_precision(self):
        c = ArvelCollection([1, 2, 3])
        assert c.percentage(lambda x: x == 1, precision=4) == 33.3333

    def test_multiply(self):
        c = ArvelCollection([1, 2])
        assert c.multiply(3).to_list() == [1, 2, 1, 2, 1, 2]

    def test_multiply_zero(self):
        c = ArvelCollection([1, 2])
        assert c.multiply(0).to_list() == []

    def test_after_value(self):
        c = ArvelCollection([1, 2, 3, 4])
        assert c.after(2) == 3

    def test_after_callable(self):
        c = ArvelCollection([1, 2, 3, 4])
        assert c.after(lambda x: x == 2) == 3

    def test_after_last_returns_none(self):
        c = ArvelCollection([1, 2, 3])
        assert c.after(3) is None

    def test_after_not_found_returns_none(self):
        c = ArvelCollection([1, 2, 3])
        assert c.after(99) is None

    def test_before_value(self):
        c = ArvelCollection([1, 2, 3, 4])
        assert c.before(3) == 2

    def test_before_callable(self):
        c = ArvelCollection([1, 2, 3, 4])
        assert c.before(lambda x: x == 3) == 2

    def test_before_first_returns_none(self):
        c = ArvelCollection([1, 2, 3])
        assert c.before(1) is None

    def test_before_not_found_returns_none(self):
        c = ArvelCollection([1, 2, 3])
        assert c.before(99) is None

    def test_select_from_dicts(self):
        c = ArvelCollection(
            [
                {"name": "Alice", "age": 30, "role": "admin"},
                {"name": "Bob", "age": 25, "role": "user"},
            ]
        )
        result = c.select("name", "age")
        assert result.to_list() == [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]

    def test_select_from_objects(self):
        c = _items()
        result = c.select("name", "role")
        assert result[0] == {"name": "Alice", "role": "admin"}

    def test_select_missing_key(self):
        c = ArvelCollection([{"name": "Alice"}])
        result = c.select("name", "missing")
        assert result.to_list() == [{"name": "Alice", "missing": None}]
