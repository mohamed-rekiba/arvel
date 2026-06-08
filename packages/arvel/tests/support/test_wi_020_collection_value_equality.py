"""Collection.intersect / diff compare by value (==), not identity.

Previously they used id(), so value-equal-but-distinct objects (runtime-built
strings, dicts, model instances) were never matched — inconsistent with
only/except_ and with Laravel's value semantics.
"""

from __future__ import annotations

from arvel.support.collections import Collection


def _rep(ch: str) -> str:
    # Built at runtime so it isn't folded into a shared constant.
    return "".join([ch] * 40)


class TestIntersectValueEquality:
    def test_runtime_strings_match_by_value(self) -> None:
        coll = Collection([_rep("x"), _rep("y"), _rep("z")])
        other = [_rep("y"), _rep("z"), _rep("w")]
        assert list(coll.intersect(other)) == [_rep("y"), _rep("z")]

    def test_unhashable_dicts_match_by_value(self) -> None:
        coll = Collection([{"id": 1}, {"id": 2}])
        assert list(coll.intersect([{"id": 2}])) == [{"id": 2}]

    def test_ints_match_by_value(self) -> None:
        assert list(Collection([1, 2, 3]).intersect([2, 3, 4])) == [2, 3]


class TestDiffValueEquality:
    def test_runtime_strings_diff_by_value(self) -> None:
        coll = Collection([_rep("x"), _rep("y"), _rep("z")])
        other = [_rep("y"), _rep("z"), _rep("w")]
        assert list(coll.diff(other)) == [_rep("x")]

    def test_unhashable_dicts_diff_by_value(self) -> None:
        coll = Collection([{"id": 1}, {"id": 2}])
        assert list(coll.diff([{"id": 2}])) == [{"id": 1}]


class TestConsistentWithOnlyExcept:
    def test_intersect_matches_only_semantics(self) -> None:
        coll = Collection([{"a": 1}, {"a": 2}, {"a": 3}])
        assert list(coll.intersect([{"a": 2}])) == list(coll.only({"a": 2}))

    def test_diff_matches_except_semantics(self) -> None:
        coll = Collection([{"a": 1}, {"a": 2}, {"a": 3}])
        assert list(coll.diff([{"a": 2}])) == list(coll.except_({"a": 2}))
