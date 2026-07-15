"""Parity-fill for arvel.support: Str/Stringable, Collection, Context, Concurrency gaps
closed against the reference's documented edge semantics (backlog 1.4 support-parity-fill)."""

from __future__ import annotations

import asyncio
import functools
import re

import pytest

from arvel.support import (
    Collection,
    Concurrency,
    Context,
    ItemNotFoundException,
    MultipleItemsFoundException,
    Str,
)

# --- Str: regex ------------------------------------------------------------


def test_match_returns_first_group_else_full_match_else_empty() -> None:
    assert Str.match(r"bar", "foo bar") == "bar"
    assert Str.match(r"foo (.*)", "foo bar") == "bar"
    assert Str.match(r"xyz", "foo bar") == ""


def test_match_all_returns_first_group_matches_or_full_matches() -> None:
    assert Str.match_all(r"bar", "bar foo bar").all() == ["bar", "bar"]
    assert Str.match_all(r"f(\w*)", "bar fun bar fly").all() == ["un", "ly"]
    assert Str.match_all(r"xyz", "bar foo bar").all() == []


def test_is_match() -> None:
    assert Str.is_match(r"foo (.*)", "foo bar") is True
    assert Str.is_match(r"foo (.*)", "nomatch") is False


def test_replace_matches_with_string_replacement() -> None:
    assert Str.replace_matches(r"[^A-Za-z0-9]+", "", "(+1) 501-555-1000") == "15015551000"


def test_replace_matches_with_callable_replacement() -> None:
    assert Str.replace_matches(r"\d", lambda m: f"[{m}]", "123") == "[1][2][3]"


# --- Str: ascii / excerpt / word_wrap ---------------------------------------


def test_ascii_transliterates_to_closest_ascii() -> None:
    assert Str.ascii_("û") == "u"
    assert Str.ascii_("café") == "cafe"


def test_excerpt_wraps_radius_around_first_phrase_match() -> None:
    assert Str.excerpt("This is my name", "my", radius=3) == "...is my na..."
    assert Str.excerpt("This is my name", "name", radius=3, omission="(...) ") == "(...) my name"
    assert Str.excerpt("This is my name", "nope") == ""


def test_word_wrap_breaks_at_nearest_prior_space() -> None:
    text = "The quick brown fox jumped over the lazy dog."
    wrapped = Str.word_wrap(text, characters=20, break_str="<br />\n")
    assert wrapped == "The quick brown fox<br />\njumped over the lazy<br />\ndog."


# --- Str: password / uuid7 ---------------------------------------------------


def test_password_default_length_and_charset() -> None:
    pw = Str.password()
    assert len(pw) == 32
    assert not any(c.isspace() for c in pw)  # spaces default False


def test_password_letters_only() -> None:
    pw = Str.password(24, letters=True, numbers=False, symbols=False, spaces=False)
    assert len(pw) == 24
    assert pw.isalpha()


def test_uuid7_is_version_7() -> None:
    value = Str.uuid7()
    assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[0-9a-f]{4}-[0-9a-f]{12}", value)


def test_uuid_default_is_version_7() -> None:
    # Str.uuid() is the central UUID generator and defaults to v7 (time-ordered)
    value = Str.uuid()
    assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[0-9a-f]{4}-[0-9a-f]{12}", value)


def test_uuid4_is_explicit_version_4() -> None:
    value = Str.uuid4()
    assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", value)


# --- Str: substr_count / substr_replace / deduplicate / base64 --------------


def test_substr_count() -> None:
    assert Str.substr_count("If you like ice cream, you will like snow cones.", "like") == 2


def test_substr_replace() -> None:
    assert Str.substr_replace("1300", ":", 2) == "13:"
    assert Str.substr_replace("1300", ":", 2, 0) == "13:00"


def test_deduplicate_default_space_and_custom_character() -> None:
    assert Str.deduplicate("The   Example   Framework") == "The Example Framework"
    assert Str.deduplicate("The---Example---Framework", "-") == "The-Example-Framework"


def test_base64_round_trip() -> None:
    assert Str.to_base64("Example") == "RXhhbXBsZQ=="
    assert Str.from_base64("RXhhbXBsZQ==") == "Example"


# --- Stringable fluent equivalents ------------------------------------------


def test_stringable_match_family() -> None:
    assert Str.of("foo bar").match(r"foo (.*)") == "bar"
    assert Str.of("bar foo bar").match_all(r"bar").all() == ["bar", "bar"]
    assert Str.of("foo bar").is_match(r"foo (.*)") is True


def test_stringable_ascii_excerpt_word_wrap_deduplicate() -> None:
    assert Str.of("û").ascii_() == "u"
    assert Str.of("This is my name").excerpt("my", radius=3) == "...is my na..."
    assert Str.of("a b c d").word_wrap(1, "|") == "a|b|c|d"
    assert Str.of("a   b").deduplicate() == "a b"


def test_stringable_substr_replace_replace_matches_and_base64() -> None:
    assert Str.of("1300").substr_replace(":", 2) == "13:"
    assert Str.of("(+1) 501-555-1000").replace_matches(r"[^A-Za-z0-9]+", "") == "15015551000"
    assert Str.of("Example").to_base64() == "RXhhbXBsZQ=="
    assert Str.of("RXhhbXBsZQ==").from_base64() == "Example"
    assert Str.of("aabaa").substr_count("aa") == 2


# --- Collection: diff / intersect / sole / first_where / contains ----------


def test_collection_diff() -> None:
    assert Collection([1, 2, 3, 4, 5]).diff([2, 4, 6, 8]).all() == [1, 3, 5]


def test_collection_intersect() -> None:
    result = Collection(["Desk", "Sofa", "Chair"]).intersect(["Desk", "Chair", "Bookcase"])
    assert result.all() == ["Desk", "Chair"]


def test_collection_sole_returns_the_single_match() -> None:
    assert Collection([1, 2, 3, 4]).sole(lambda v: v == 2) == 2
    assert Collection([1]).sole() == 1


def test_collection_sole_raises_on_zero_or_many_matches() -> None:
    with pytest.raises(ItemNotFoundException):
        Collection([1, 2, 3]).sole(lambda v: v == 99)
    with pytest.raises(MultipleItemsFoundException):
        Collection([1, 1, 2]).sole(lambda v: v == 1)


def test_collection_first_where_one_two_and_three_arg_forms() -> None:
    people = Collection(
        [
            {"name": "Regena", "age": None},
            {"name": "Linda", "age": 14},
            {"name": "Diego", "age": 23},
            {"name": "Linda", "age": 84},
        ]
    )
    assert people.first_where("name", "Linda") == {"name": "Linda", "age": 14}
    assert people.first_where("age", ">=", 18) == {"name": "Diego", "age": 23}
    assert people.first_where("age") == {"name": "Linda", "age": 14}


def test_collection_contains_accepts_a_callable() -> None:
    items = Collection([1, 2, 3, 4, 5])
    assert items.contains(lambda v: v > 5) is False
    assert items.contains(lambda v: v == 3) is True
    assert items.contains(3) is True


# --- Collection: random / shuffle / median / mode ---------------------------


def test_collection_random_single_and_n() -> None:
    items = Collection([1, 2, 3, 4, 5])
    assert items.random() in [1, 2, 3, 4, 5]
    picked = items.random(3)
    assert isinstance(picked, Collection)
    assert len(picked) == 3
    assert all(v in [1, 2, 3, 4, 5] for v in picked)


def test_collection_random_raises_when_requesting_more_than_available() -> None:
    with pytest.raises(ValueError, match="only 3 available"):
        Collection([1, 2, 3]).random(5)


def test_collection_shuffle_preserves_multiset() -> None:
    items = Collection([1, 2, 3, 4, 5])
    shuffled = items.shuffle()
    assert sorted(shuffled.all()) == [1, 2, 3, 4, 5]


def test_collection_median() -> None:
    assert Collection([{"foo": 10}, {"foo": 10}, {"foo": 20}, {"foo": 40}]).median("foo") == 15
    assert Collection([1, 1, 2, 4]).median() == 1.5


def test_collection_mode() -> None:
    assert Collection([{"foo": 10}, {"foo": 10}, {"foo": 20}, {"foo": 40}]).mode("foo") == [10]
    assert Collection([1, 1, 2, 4]).mode() == [1]
    assert Collection([1, 1, 2, 2]).mode() == [1, 2]


# --- Collection: pad / splice ------------------------------------------------


def test_collection_pad_right_and_left() -> None:
    assert Collection(["A", "B", "C"]).pad(5, 0).all() == ["A", "B", "C", 0, 0]
    assert Collection(["A", "B", "C"]).pad(-5, 0).all() == [0, 0, "A", "B", "C"]
    assert Collection(["A", "B", "C"]).pad(2, 0).all() == [
        "A",
        "B",
        "C",
    ]  # no-op: already >= |size|


def test_collection_splice_removes_and_mutates_in_place() -> None:
    collection = Collection([1, 2, 3, 4, 5])
    chunk = collection.splice(2)
    assert chunk.all() == [3, 4, 5]
    assert collection.all() == [1, 2]

    collection = Collection([1, 2, 3, 4, 5])
    chunk = collection.splice(2, 1)
    assert chunk.all() == [3]
    assert collection.all() == [1, 2, 4, 5]

    collection = Collection([1, 2, 3, 4, 5])
    chunk = collection.splice(2, 1, [10, 11])
    assert chunk.all() == [3]
    assert collection.all() == [1, 2, 10, 11, 4, 5]


# --- Context -----------------------------------------------------------------


async def test_context_only_and_except() -> None:
    Context.add("a", 1)
    Context.add("b", 2)
    Context.add("c", 3)
    assert Context.only(["a", "b"]) == {"a": 1, "b": 2}
    assert Context.except_(["a"]) == {"b": 2, "c": 3}
    Context.forget("a")
    Context.forget("b")
    Context.forget("c")


async def test_context_pull_reads_and_removes() -> None:
    Context.add("k", "v")
    assert Context.pull("k") == "v"
    assert Context.has("k") is False
    assert Context.pull("missing", "default") == "default"


async def test_context_remember_only_computes_once() -> None:
    calls = []

    def factory() -> str:
        calls.append(1)
        return "computed"

    assert Context.remember("memo", factory) == "computed"
    assert Context.remember("memo", factory) == "computed"
    assert len(calls) == 1
    Context.forget("memo")


async def test_context_when_invokes_then_or_otherwise() -> None:
    Context.when(True, lambda ctx: ctx.add("flag", "yes"), lambda ctx: ctx.add("flag", "no"))
    assert Context.get("flag") == "yes"
    Context.when(False, lambda ctx: ctx.add("flag", "yes"), lambda ctx: ctx.add("flag", "no"))
    assert Context.get("flag") == "no"
    Context.forget("flag")


async def test_context_missing() -> None:
    assert Context.missing("nope") is True
    Context.add("nope", None)
    assert Context.missing("nope") is False  # has() counts a stored None
    Context.forget("nope")


# --- Concurrency ---------------------------------------------------------------


async def test_concurrency_run_with_dict_returns_dict_keyed_results() -> None:
    async def double(n: int) -> int:
        return n * 2

    results = await Concurrency.run(
        {"a": functools.partial(double, 1), "b": functools.partial(double, 2)}
    )
    assert results == {"a": 2, "b": 4}


async def test_concurrency_run_with_list_still_returns_a_list() -> None:
    results = await Concurrency.run([lambda: 1, lambda: 2])
    assert results == [1, 2]


async def test_concurrency_run_timeout_raises_on_slow_task() -> None:
    async def slow() -> int:
        await asyncio.sleep(1)
        return 1

    with pytest.raises(TimeoutError):
        await Concurrency.run([slow], timeout=0.01)


async def test_concurrency_run_timeout_does_not_affect_fast_tasks() -> None:
    async def fast() -> int:
        return 1

    results = await Concurrency.run([fast], timeout=5)
    assert results == [1]


def test_password_contains_every_enabled_class() -> None:
    from arvel.support import Str

    for _ in range(20):  # probabilistic bug would slip a single run
        pw = Str.password(8, letters=True, numbers=True, symbols=True)
        assert any(c.isalpha() for c in pw)
        assert any(c.isdigit() for c in pw)
        assert any(not c.isalnum() for c in pw)


def test_first_where_unknown_operator_raises() -> None:
    import pytest

    from arvel.support import Collection

    with pytest.raises(ValueError, match="unknown operator"):
        Collection([{"a": 1}]).first_where("a", "~=", 1)
