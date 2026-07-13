"""Collection — filtering/selection helpers: where_in / where_not_in / where_null /
where_not_null / take. Keyed by an item attribute or dict key (same ``_get`` resolution as ``where``)."""

from __future__ import annotations

from arvel.support import Collection


def test_where_in_and_where_not_in() -> None:
    c = Collection([{"role": "admin"}, {"role": "user"}, {"role": "guest"}])
    assert c.where_in("role", ["admin", "user"]).all() == [{"role": "admin"}, {"role": "user"}]
    assert c.where_not_in("role", ["admin", "user"]).all() == [{"role": "guest"}]


def test_where_null_and_where_not_null() -> None:
    # missing key resolves to None (via _get), so it groups with explicit None
    c = Collection([{"x": 1}, {"x": None}, {"y": 2}])
    assert c.where_null("x").all() == [{"x": None}, {"y": 2}]
    assert c.where_not_null("x").all() == [{"x": 1}]


def test_take_positive_negative_zero() -> None:
    c = Collection([1, 2, 3, 4, 5])
    assert c.take(2).all() == [1, 2]  # first 2
    assert c.take(-2).all() == [4, 5]  # last 2 (negative, parity)
    assert c.take(0).all() == []


def test_filtering_is_chainable_and_returns_new_collection() -> None:
    c = Collection([{"role": "admin", "active": True}, {"role": "user", "active": None}])
    out = c.where_not_null("active").where_in("role", ["admin"])
    assert isinstance(out, Collection)
    assert out.all() == [{"role": "admin", "active": True}]
