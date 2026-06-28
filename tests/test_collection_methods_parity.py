"""Collection parity (Laravel): common methods that were absent — aggregates (avg/max/min/count_by),
reject/every/partition/search/value, ordering (reverse/sort_desc/sort_by_desc/skip/slice/nth),
combining (merge/concat/flat_map/implode/join), and fluent control flow (tap/pipe/when/unless)."""

from __future__ import annotations

from arvel.support import Collection


def test_aggregates() -> None:
    c = Collection([1, 2, 3, 4, 5])
    assert c.avg() == 3.0
    assert c.max() == 5
    assert c.min() == 1
    assert Collection([]).avg() is None  # Laravel: null on empty, not a crash
    assert Collection([]).max() is None
    assert Collection([1, 1, 2, 3, 3, 3]).count_by() == {1: 2, 2: 1, 3: 3}
    assert Collection([{"t": "x"}, {"t": "y"}, {"t": "x"}]).count_by("t") == {"x": 2, "y": 1}


def test_filtering_and_selection() -> None:
    c = Collection([1, 2, 3, 4, 5])
    assert c.reject(lambda x: x % 2 == 0).all() == [1, 3, 5]
    assert c.every(lambda x: x > 0) is True
    assert c.every(lambda x: x > 2) is False
    yes, no = c.partition(lambda x: x % 2 == 0)
    assert yes.all() == [2, 4] and no.all() == [1, 3, 5]
    assert c.search(3) == 2
    assert c.search(lambda x: x > 3) == 3
    assert c.search(99) is None
    assert Collection([{"name": "Ada"}]).value("name") == "Ada"


def test_ordering_and_slicing() -> None:
    c = Collection([1, 2, 3, 4, 5])
    assert c.reverse().all() == [5, 4, 3, 2, 1]
    assert c.sort_desc().all() == [5, 4, 3, 2, 1]
    assert c.skip(2).all() == [3, 4, 5]
    assert c.slice(1, 2).all() == [2, 3]
    assert c.nth(2).all() == [1, 3, 5]
    assert Collection([{"a": 1}, {"a": 3}, {"a": 2}]).sort_by_desc("a").pluck("a").all() == [
        3,
        2,
        1,
    ]


def test_combining() -> None:
    c = Collection([1, 2, 3])
    assert c.merge([4, 5]).all() == [1, 2, 3, 4, 5]
    assert c.concat([6]).all() == [1, 2, 3, 6]
    assert Collection([[1, 2], [3]]).flat_map(lambda x: x).all() == [1, 2, 3]
    assert c.implode("-") == "1-2-3"
    assert Collection([{"n": "a"}, {"n": "b"}]).join(", ", "n") == "a, b"


def test_fluent_control_flow() -> None:
    c = Collection([1, 2, 3, 4, 5])
    captured: list[int] = []
    assert c.tap(lambda col: captured.append(col.sum())) is c
    assert captured == [15]
    assert c.pipe(lambda col: col.sum()) == 15
    assert c.when(True, lambda col: col.filter(lambda x: x > 3)).all() == [4, 5]
    assert c.when(False, lambda col: col.filter(lambda x: x > 3)).all() == [1, 2, 3, 4, 5]
    assert c.unless(False, lambda col: col.reject(lambda x: x > 3)).all() == [1, 2, 3]
