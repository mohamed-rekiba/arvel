"""Small-surface coverage: ``Str`` edge-guards, ``Collection.when`` default branch + attr-keyed
``_get``, ``LazyCollection`` terminal ops, and the ``CursorPaginator`` accessors."""

from __future__ import annotations

from arvel.pagination import CursorPaginator
from arvel.support import Collection, LazyCollection, Str


# --- Str edge guards ------------------------------------------------------
def test_str_edge_guards() -> None:
    assert Str.between("hello", "", "o") == "hello"  # empty delimiter -> value unchanged
    assert Str.replace_first("", "X", "abc") == "abc"  # empty search -> unchanged
    assert Str.replace_last("z", "X", "abc") == "abc"  # search absent -> unchanged
    assert Str.replace_array("_", ["a", "b"], "no-placeholder") == "no-placeholder"  # break
    assert Str.swap({}, "abc") == "abc"  # no replacements -> unchanged


# --- Collection -----------------------------------------------------------
def test_collection_when_default_branch_and_attr_get() -> None:
    called: list[str] = []
    result = Collection([1, 2]).when(
        False, lambda c: called.append("active"), default=lambda c: called.append("default")
    )
    assert called == ["default"]
    assert isinstance(result, Collection)

    class _Row:
        def __init__(self, name: str) -> None:
            self.name = name

    plucked = Collection([_Row("a"), _Row("b")]).pluck("name").to_list()
    assert plucked == ["a", "b"]  # _get via getattr on non-dict items


# --- LazyCollection terminal ops ------------------------------------------
def test_lazy_collection_each_all_collect() -> None:
    seen: list[int] = []
    lazy = LazyCollection([1, 2, 3])
    assert lazy.each(seen.append) is lazy
    assert seen == [1, 2, 3]
    assert lazy.all() == [1, 2, 3]
    collected = lazy.collect()
    assert isinstance(collected, Collection)
    assert collected.to_list() == [1, 2, 3]


# --- CursorPaginator ------------------------------------------------------
def test_cursor_paginator_accessors() -> None:
    page = CursorPaginator(
        [10, 20, 30],
        per_page=3,
        next_cursor="nxt",
        prev_cursor=None,
        path="/feed",
        query={"tag": "python"},
        cursor_name="cursor",
    )
    assert page.items().to_list() == [10, 20, 30]
    assert page.per_page() == 3
    assert page.count() == 3
    assert page.is_empty() is False
    assert page.is_not_empty() is True
    assert page.on_first_page() is True
    assert page.has_more_pages() is True
    assert page.path() == "/feed"
    assert page.next_page_url() == "/feed?tag=python&cursor=nxt"
    assert page.previous_page_url() is None  # no prev cursor
    assert list(page) == [10, 20, 30]
    assert len(page) == 3
    assert page[1] == 20


def test_cursor_paginator_empty_page() -> None:
    page = CursorPaginator([], per_page=5, path="/x")
    assert page.is_empty() is True
    assert page.is_not_empty() is False
