"""More validation rules that were SILENT no-ops (`_check`'s `case _: return True`) — every one
silently accepted bad data. Implements size / digits / digits_between / alpha_dash / json / ip and the
field-comparison family gt/gte/lt/lte."""

from __future__ import annotations

import pytest

from arvel.validation import ValidationException, Validator


def _passes(data: dict, rules: dict) -> bool:
    try:
        Validator(data, rules).validate()
        return True
    except ValidationException:
        return False


def test_size_rule() -> None:
    assert _passes({"x": "abc"}, {"x": "size:3"})  # string length
    assert not _passes({"x": "ab"}, {"x": "size:3"})
    assert _passes({"x": "3"}, {"x": "numeric|size:3"})  # numeric value, not length
    assert _passes({"x": ["a", "b"]}, {"x": "size:2"})  # array count


def test_digits_rules() -> None:
    assert _passes({"x": "1234"}, {"x": "digits:4"})
    assert not _passes({"x": "12"}, {"x": "digits:4"})  # wrong length
    assert not _passes({"x": "12ab"}, {"x": "digits:4"})  # not all digits
    assert _passes({"x": "123"}, {"x": "digits_between:2,4"})
    assert not _passes({"x": "1"}, {"x": "digits_between:2,4"})


def test_gt_gte_lt_lte_compare_fields() -> None:
    # gt:other_field — compare sizes; numeric rule makes it a value comparison
    assert _passes({"a": "10", "b": "5"}, {"a": "numeric|gt:b"})
    assert not _passes({"a": "3", "b": "5"}, {"a": "numeric|gt:b"})
    assert _passes({"a": "5", "b": "5"}, {"a": "numeric|gte:b"})
    assert _passes({"a": "3", "b": "5"}, {"a": "numeric|lt:b"})
    assert not _passes({"a": "9", "b": "5"}, {"a": "numeric|lte:b"})
    # without a numeric rule, size is string length
    assert _passes({"a": "abcd", "b": "xy"}, {"a": "gt:b"})


def test_alpha_dash_json_ip() -> None:
    assert _passes({"x": "a-b_c1"}, {"x": "alpha_dash"})
    assert not _passes({"x": "a b!"}, {"x": "alpha_dash"})
    assert _passes({"x": '{"a": 1}'}, {"x": "json"})
    assert not _passes({"x": "{not json"}, {"x": "json"})
    assert _passes({"x": "192.168.1.1"}, {"x": "ip"})
    assert _passes({"x": "::1"}, {"x": "ip"})  # IPv6
    assert not _passes({"x": "999.999.0.1"}, {"x": "ip"})
    assert not _passes({"x": 12345}, {"x": "ip"})  # ip requires a string, not a bare int


def test_new_rules_have_messages() -> None:
    with pytest.raises(ValidationException) as exc:
        Validator({"x": "999.999.0.1"}, {"x": "ip"}).validate()
    assert "valid IP address" in str(exc.value)
