"""Spec 12 §2 — strings, numbers, types/formats, arrays. Table-driven pass+fail per rule."""

from __future__ import annotations

import pytest

from arvel.validation import Validator


# -- strings ------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("rule", "good", "bad"),
    [
        ("uppercase", "ABC123", "ABc"),
        ("lowercase", "abc123", "aBc"),
        ("ascii", "hello!", "héllo"),
        ("ulid", "01ARZ3NDEKTSV4RRFFQ69G5FAV", "not-a-ulid"),
    ],
)
def test_string_rules(rule: str, good: str, bad: str) -> None:
    assert Validator({"s": good}, {"s": rule}).passes()
    assert Validator({"s": bad}, {"s": rule}).fails()


def test_not_regex() -> None:
    assert Validator({"s": "abc"}, {"s": r"not_regex:^\d+$"}).passes()
    assert Validator({"s": "123"}, {"s": r"not_regex:^\d+$"}).fails()


def test_doesnt_start_with() -> None:
    assert Validator({"s": "xyz"}, {"s": "doesnt_start_with:a,b"}).passes()
    assert Validator({"s": "abc"}, {"s": "doesnt_start_with:a,b"}).fails()


def test_doesnt_end_with() -> None:
    assert Validator({"s": "xyz"}, {"s": "doesnt_end_with:a,b"}).passes()
    assert Validator({"s": "xya"}, {"s": "doesnt_end_with:a,b"}).fails()


def test_contains_array_must_contain_all() -> None:
    assert Validator({"a": ["x", "y", "z"]}, {"a": "contains:x,y"}).passes()
    assert Validator({"a": ["x"]}, {"a": "contains:x,y"}).fails()
    assert Validator({"a": "not-a-list"}, {"a": "contains:x"}).fails()


# -- numbers ------------------------------------------------------------------------------------
def test_decimal_places_range() -> None:
    assert Validator({"p": "12.345"}, {"p": "decimal:2,3"}).passes()
    assert Validator({"p": "12.3456"}, {"p": "decimal:2,3"}).fails()
    assert Validator({"p": "12"}, {"p": "decimal:2"}).fails()  # 0 places, needs exactly 2
    assert Validator({"p": "12.34"}, {"p": "decimal:2"}).passes()


def test_multiple_of() -> None:
    assert Validator({"n": 10}, {"n": "multiple_of:5"}).passes()
    assert Validator({"n": 7}, {"n": "multiple_of:5"}).fails()
    assert Validator({"n": "10"}, {"n": "multiple_of:5"}).passes()


def test_multiple_of_bool_trap() -> None:
    # bool is a subclass of int in Python — must NOT sneak through as 0/1
    assert Validator({"n": True}, {"n": "multiple_of:1"}).fails()


def test_min_max_digits() -> None:
    assert Validator({"n": "12345"}, {"n": "min_digits:3"}).passes()
    assert Validator({"n": "12"}, {"n": "min_digits:3"}).fails()
    assert Validator({"n": "12"}, {"n": "max_digits:3"}).passes()
    assert Validator({"n": "12345"}, {"n": "max_digits:3"}).fails()


# -- types / formats ----------------------------------------------------------------------------
def test_timezone() -> None:
    assert Validator({"t": "Europe/Paris"}, {"t": "timezone"}).passes()
    assert Validator({"t": "Not/AZone"}, {"t": "timezone"}).fails()


def test_ipv4_ipv6() -> None:
    assert Validator({"i": "192.168.1.1"}, {"i": "ipv4"}).passes()
    assert Validator({"i": "::1"}, {"i": "ipv4"}).fails()  # v6 given to ipv4
    assert Validator({"i": "::1"}, {"i": "ipv6"}).passes()
    assert Validator({"i": "192.168.1.1"}, {"i": "ipv6"}).fails()  # v4 given to ipv6


def test_mac_address() -> None:
    assert Validator({"m": "00:1B:44:11:3A:B7"}, {"m": "mac_address"}).passes()
    assert Validator({"m": "00-1B-44-11-3A-B7"}, {"m": "mac_address"}).passes()
    assert Validator({"m": "not-a-mac"}, {"m": "mac_address"}).fails()


# -- arrays -------------------------------------------------------------------------------------
def test_in_array() -> None:
    data = {"selected": 2, "options": [1, 2, 3]}
    assert Validator(data, {"selected": "in_array:options.*"}).passes()
    assert Validator(
        {"selected": 9, "options": [1, 2, 3]}, {"selected": "in_array:options.*"}
    ).fails()


def test_distinct_wildcard_sibling_uniqueness() -> None:
    data = {"items": [{"sku": "a"}, {"sku": "b"}]}
    assert Validator(data, {"items.*.sku": "distinct"}).passes()
    dup = {"items": [{"sku": "a"}, {"sku": "a"}]}
    v = Validator(dup, {"items.*.sku": "distinct"})
    assert v.fails()
    assert "items.1.sku" in v.errors()  # the SECOND occurrence is flagged


def test_list_rule() -> None:
    assert Validator({"a": [1, 2]}, {"a": "list"}).passes()
    assert Validator({"a": "nope"}, {"a": "list"}).fails()
