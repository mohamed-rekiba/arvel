"""Request input surface (H6): all/only/except/has/filled/merge + typed getters/collect.

Test-first, driven off a fake ``litestar``-shaped raw request (same style as
``test_request_input_helpers.py``) so the accessors are exercised without a running kernel."""

from __future__ import annotations

from enum import Enum
from typing import Any

from arvel.dates import Date
from arvel.http.request import Request
from arvel.support import Collection


class _Raw:
    def __init__(self, body: Any = None, query: dict[str, str] | None = None) -> None:
        self._body = body if body is not None else {}
        self.query_params = query or {}

    async def json(self) -> Any:
        return self._body


def _req(body: Any = None, query: dict[str, str] | None = None) -> Request:
    return Request(_Raw(body, query))


# --- all() / merge -----------------------------------------------------------------------


async def test_all_merges_query_then_body_then_overlay() -> None:
    r = _req(body={"a": "body-a", "b": "body-b"}, query={"a": "query-a", "c": "query-c"})
    data = await r.all()
    assert data == {"a": "body-a", "b": "body-b", "c": "query-c"}  # body wins over query
    r.merge({"a": "overlay-a", "d": "overlay-d"})
    assert await r.all() == {
        "a": "overlay-a",  # overlay wins over everything
        "b": "body-b",
        "c": "query-c",
        "d": "overlay-d",
    }


async def test_all_ignores_a_non_dict_or_absent_body() -> None:
    class _RaisingRaw(_Raw):
        async def json(self) -> Any:
            raise ValueError("not json")

    r = Request(_RaisingRaw(query={"q": "x"}))
    assert await r.all() == {"q": "x"}


async def test_merge_if_missing_does_not_override_a_prior_merge() -> None:
    r = _req(body={})
    r.merge({"a": "explicit"})
    await r.merge_if_missing({"a": "default", "b": "default-b"})
    assert await r.all() == {"a": "explicit", "b": "default-b"}


async def test_merge_if_missing_does_not_override_a_body_key_and_merges_a_missing_one() -> None:
    r = _req(body={"a": "from-body"})
    await r.merge_if_missing({"a": "should-not-win", "b": "merged-default"})
    assert await r.all() == {"a": "from-body", "b": "merged-default"}


async def test_merge_returns_self_for_chaining() -> None:
    r = _req(body={})
    assert r.merge({"x": 1}) is r
    assert await r.merge_if_missing({"y": 2}) is r


# --- input() dot-notation -----------------------------------------------------------------


async def test_input_dot_notation_reads_nested_body() -> None:
    r = _req(body={"user": {"name": "ada", "address": {"city": "london"}}})
    assert await r.input("user.name") == "ada"
    assert await r.input("user.address.city") == "london"


async def test_input_dot_notation_absent_returns_default() -> None:
    r = _req(body={"user": {"name": "ada"}})
    assert await r.input("user.missing", "fallback") == "fallback"
    assert await r.input("nope.nope") is None


async def test_input_no_key_returns_all() -> None:
    r = _req(body={"a": 1}, query={"b": "2"})
    assert await r.input() == await r.all()


async def test_input_plain_key_still_prefers_body_then_query() -> None:
    r = _req(body={"a": 1}, query={"b": "2"})
    assert await r.input("a") == 1
    assert await r.input("b") == "2"
    assert await r.input("missing", "d") == "d"


# --- only / except -------------------------------------------------------------------------


async def test_only_narrows_and_ignores_absent_keys() -> None:
    r = _req(body={"a": 1, "b": 2, "c": 3})
    assert await r.only(["a", "c", "z"]) == {"a": 1, "c": 3}


async def test_except_removes_keys() -> None:
    r = _req(body={"a": 1, "b": 2, "c": 3})
    assert await r.except_(["b"]) == {"a": 1, "c": 3}


# --- has / has_any / filled / missing -------------------------------------------------------


async def test_has_true_only_when_present_even_if_empty() -> None:
    r = _req(body={"a": "", "b": None})
    assert await r.has("a") is True
    assert await r.has("b") is True
    assert await r.has("missing") is False
    assert await r.has(["a", "b"]) is True
    assert await r.has(["a", "missing"]) is False


async def test_has_any() -> None:
    r = _req(body={"a": 1})
    assert await r.has_any(["missing", "a"]) is True
    assert await r.has_any(["missing", "also_missing"]) is False


async def test_filled_false_on_empty_string_and_absent_true_on_real_value() -> None:
    r = _req(body={"a": "", "b": "x", "c": [], "d": {}})
    assert await r.filled("a") is False
    assert await r.filled("b") is True
    assert await r.filled("c") is False
    assert await r.filled("d") is False
    assert await r.filled("missing") is False


async def test_missing_is_inverse_of_has() -> None:
    r = _req(body={"a": 1})
    assert await r.missing("a") is False
    assert await r.missing("b") is True


# --- typed getters ---------------------------------------------------------------------------


async def test_string_getter_coerces_and_defaults() -> None:
    r = _req(body={"n": 5})
    assert await r.string("n") == "5"
    assert await r.string("missing", "d") == "d"
    assert await r.string("missing") == ""


async def test_integer_getter_coerces_and_falls_back_on_value_error() -> None:
    r = _req(body={"n": "5", "bad": "not-a-number"})
    assert await r.integer("n") == 5
    assert await r.integer("bad") == 0
    assert await r.integer("bad", default=9) == 9
    assert await r.integer("missing") == 0


async def test_date_getter_parses_and_falls_back_on_unparseable() -> None:
    r = _req(body={"d": "2024-01-15", "bad": "not-a-date"})
    parsed = await r.date("d")
    assert isinstance(parsed, Date)
    assert parsed.to_iso().startswith("2024-01-15")
    assert await r.date("bad") is None
    sentinel = object()
    assert await r.date("missing", sentinel) is sentinel


class _Color(Enum):
    RED = "red"
    BLUE = "blue"


async def test_enum_getter_resolves_by_value_or_none() -> None:
    r = _req(body={"c": "red", "bad": "purple"})
    assert await r.enum("c", _Color) is _Color.RED
    assert await r.enum("bad", _Color) is None
    assert await r.enum("missing", _Color) is None


async def test_collect_wraps_all_when_no_key() -> None:
    r = _req(body={"a": 1, "b": 2})
    coll = await r.collect()
    assert isinstance(coll, Collection)
    assert set(coll.all()) == {("a", 1), ("b", 2)}


async def test_collect_wraps_a_key_as_a_list() -> None:
    r = _req(body={"tags": ["x", "y"], "single": "z"})
    assert (await r.collect("tags")).all() == ["x", "y"]
    assert (await r.collect("single")).all() == ["z"]
    assert (await r.collect("missing")).all() == []


async def test_integer_returns_default_for_list_and_dict_values() -> None:
    request = _req({"age": [], "meta": {}})
    assert await request.integer("age", 7) == 7
    assert await request.integer("meta", 9) == 9
