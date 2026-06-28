"""Validation parity (Laravel): nested dot-path fields resolve into nested data (``user.email``), and the
``array``/``between``/``not_in``/``starts_with``/``ends_with``/``uuid`` rules actually enforce (they were
silent no-ops via the ``case _: return True`` default — silently accepting bad data)."""

from __future__ import annotations

import pytest

from arvel.validation import ValidationException, Validator


def _passes(data: dict, rules: dict) -> bool:
    try:
        Validator(data, rules).validate()
        return True
    except ValidationException:
        return False


def test_nested_dot_path_resolves_into_nested_data() -> None:
    assert _passes({"user": {"email": "a@b.com"}}, {"user.email": "email"})  # valid nested → passes
    assert not _passes(
        {"user": {"email": "nope"}}, {"user.email": "email"}
    )  # invalid nested → fails
    assert not _passes({"user": {}}, {"user.email": "required"})  # missing nested → required fails


def test_array_rule_rejects_non_lists() -> None:
    assert _passes({"tags": ["a", "b"]}, {"tags": "array"})
    assert not _passes({"tags": "a"}, {"tags": "array"})  # was a silent PASS before


def test_between_rule_enforces_size() -> None:
    assert _passes({"x": "abc"}, {"x": "between:1,5"})  # string length 3
    assert not _passes({"x": "toolong"}, {"x": "between:1,5"})  # length 7
    assert not _passes({"age": "99"}, {"age": "numeric|between:1,5"})  # numeric value out of range
    assert _passes({"age": "3"}, {"age": "numeric|between:1,5"})


def test_new_string_rules() -> None:
    assert not _passes({"x": "c"}, {"x": "not_in:a,b,c"})
    assert _passes({"x": "d"}, {"x": "not_in:a,b,c"})
    assert not _passes({"x": "hello"}, {"x": "starts_with:foo,bar"})
    assert _passes({"x": "barstool"}, {"x": "starts_with:foo,bar"})
    assert _passes({"x": "photo.png"}, {"x": "ends_with:.png,.jpg"})
    assert not _passes({"x": "doc.pdf"}, {"x": "ends_with:.png,.jpg"})


def test_uuid_rule() -> None:
    assert _passes({"id": "550e8400-e29b-41d4-a716-446655440000"}, {"id": "uuid"})
    assert not _passes({"id": "not-a-uuid"}, {"id": "uuid"})


def test_new_rules_have_helpful_messages() -> None:
    with pytest.raises(ValidationException) as exc:
        Validator({"tags": "x"}, {"tags": "array"}).validate()
    assert "must be an array" in str(exc.value)
