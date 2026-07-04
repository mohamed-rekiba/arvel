"""Collection additions (story 02): `sum`/`avg` accepting a key or callable, `zip`/`combine`/
`duplicates`, and `when_empty`/`when_not_empty`. No higher-order proxy (DR-0031) — lambdas are
the idiom."""

from __future__ import annotations

from arvel.support import Collection


def test_sum_still_works_with_no_key() -> None:
    assert Collection([1, 2, 3]).sum() == 6


def test_sum_accepts_a_string_key() -> None:
    assert Collection([{"n": 1}, {"n": 2}]).sum("n") == 3


def test_sum_accepts_a_callable() -> None:
    assert Collection([{"n": 1}, {"n": 2}]).sum(lambda r: r["n"] * 10) == 30


def test_avg_still_works_with_no_key() -> None:
    assert Collection([1, 2, 3, 4]).avg() == 2.5
    assert Collection([]).avg() is None


def test_avg_accepts_a_string_key_and_callable() -> None:
    rows = [{"n": 1}, {"n": 2}]
    assert Collection(rows).avg("n") == 1.5
    assert Collection(rows).avg(lambda r: r["n"]) == 1.5


def test_zip_pairs_items_index_wise() -> None:
    zipped = Collection([1, 2, 3]).zip([4, 5, 6])
    assert [row.all() for row in zipped] == [[1, 4], [2, 5], [3, 6]]


def test_zip_supports_multiple_iterables() -> None:
    zipped = Collection([1, 2]).zip([3, 4], [5, 6])
    assert [row.all() for row in zipped] == [[1, 3, 5], [2, 4, 6]]


def test_combine_uses_self_as_keys_and_argument_as_values() -> None:
    combined = Collection(["a", "b"]).combine([1, 2])
    assert combined == {"a": 1, "b": 2}


def test_duplicates_preserves_first_seen_order_and_indexes() -> None:
    dupes = Collection([1, 2, 1, 3, 2, 2]).duplicates()
    assert dupes == {2: 1, 4: 2, 5: 2}


def test_duplicates_accepts_a_key() -> None:
    rows = [{"n": "a"}, {"n": "b"}, {"n": "a"}]
    dupes = Collection(rows).duplicates("n")
    assert dupes == {2: {"n": "a"}}


def test_duplicates_accepts_a_callable() -> None:
    dupes = Collection([1, 2, 1]).duplicates(lambda n: n)
    assert dupes == {2: 1}


def test_when_empty_invokes_only_on_empty() -> None:
    calls: list[str] = []
    Collection([]).when_empty(lambda c: calls.append("empty"))
    Collection([1]).when_empty(lambda c: calls.append("not-empty"))
    assert calls == ["empty"]


def test_when_not_empty_invokes_only_when_not_empty() -> None:
    calls: list[str] = []
    Collection([1]).when_not_empty(lambda c: calls.append("not-empty"))
    Collection([]).when_not_empty(lambda c: calls.append("empty"))
    assert calls == ["not-empty"]


def test_when_empty_callback_result_wins_when_it_returns_a_collection() -> None:
    result = Collection([]).when_empty(lambda c: Collection([1, 2]))
    assert result.all() == [1, 2]


def test_when_empty_returns_self_when_not_empty() -> None:
    original = Collection([1, 2])
    assert original.when_empty(lambda c: Collection([9])) is original
