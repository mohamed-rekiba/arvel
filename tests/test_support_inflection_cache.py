"""Support — Str inflection is memoized (pure string→string over regex-heavy inflection).

Correctness must be unchanged; ulid() and predicates must NOT be cached.
"""

from __future__ import annotations

from arvel.support import Str


def test_inflection_results_unchanged() -> None:
    assert Str.snake("FooBar") == "foo_bar"
    assert Str.studly("foo_bar") == "FooBar"
    assert Str.camel("foo_bar") == "fooBar"
    assert Str.kebab("FooBar") == "foo-bar"
    assert Str.plural("category") == "categories"
    assert Str.singular("categories") == "category"
    assert Str.headline("foo_bar_baz") == "Foo Bar Baz"


def test_snake_is_cached_on_repeat() -> None:
    Str.snake.cache_clear()  # type: ignore[attr-defined]
    Str.snake("UserProfile")
    misses = Str.snake.cache_info().misses  # type: ignore[attr-defined]
    Str.snake("UserProfile")
    info = Str.snake.cache_info()  # type: ignore[attr-defined]
    assert info.hits >= 1
    assert info.misses == misses  # same input → no new miss


def test_ulid_is_not_cached() -> None:
    # ulid() must produce a fresh value every call — caching it would be a bug.
    assert Str.ulid() != Str.ulid()
    assert not hasattr(Str.ulid, "cache_info")
