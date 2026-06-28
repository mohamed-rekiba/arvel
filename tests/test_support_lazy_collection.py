"""Support (doc 06) — LazyCollection: deferred, generator-backed Collection. Test-first."""

from __future__ import annotations

from arvel.support import Collection, LazyCollection


def test_collection_lazy_returns_lazy_collection() -> None:
    lazy = Collection([1, 2, 3]).lazy()
    assert isinstance(lazy, LazyCollection)
    assert lazy.to_list() == [1, 2, 3]


def test_map_and_filter_are_deferred_until_materialized() -> None:
    seen: list[int] = []

    def spy(x: int) -> int:
        seen.append(x)
        return x * 2

    pipeline = LazyCollection([1, 2, 3, 4]).map(spy).filter(lambda x: x > 4)
    assert seen == []  # nothing ran yet — deferred
    result = pipeline.to_list()
    assert result == [6, 8]
    assert seen == [1, 2, 3, 4]  # ran exactly once, on materialization


def test_take_limits_without_consuming_the_rest() -> None:
    consumed: list[int] = []

    def gen() -> object:
        for i in range(1000):
            consumed.append(i)
            yield i

    first_three = LazyCollection(gen).take(3).to_list()
    assert first_three == [0, 1, 2]
    assert consumed == [0, 1, 2]  # the generator was not drained past 3


def test_first_returns_first_or_default() -> None:
    assert LazyCollection([10, 20]).first() == 10
    assert LazyCollection([]).first(default=-1) == -1


def test_list_backed_lazy_is_reiterable() -> None:
    lazy = Collection([1, 2, 3]).lazy()
    assert lazy.to_list() == [1, 2, 3]
    assert lazy.to_list() == [1, 2, 3]  # re-iterable for a list-backed source
