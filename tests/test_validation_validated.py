"""Validation (doc 10) — ``validated()`` returns the validated subset with nesting preserved
(Laravel ``$validator->validated()``). A ``user.email`` rule validates the nested value via dot-path,
so ``validated()`` must rebuild that nesting — not drop the field or return a flat ``"user.email"`` key.
"""

from __future__ import annotations

from arvel.validation import Validator


def test_validated_returns_only_ruled_fields_flat() -> None:
    data = {"name": "Ada", "email": "ada@example.com", "extra": "drop me"}
    v = Validator(data, {"name": "required", "email": "required"})
    assert not v.fails()
    assert v.validated() == {"name": "Ada", "email": "ada@example.com"}  # `extra` excluded


def test_validated_rebuilds_nested_dot_keys() -> None:
    # the bug: a passing `user.email` rule was silently dropped from validated()
    data = {"user": {"email": "ada@example.com", "name": "Ada", "secret": "x"}, "junk": 1}
    v = Validator(data, {"user.email": "required", "user.name": "required"})
    assert not v.fails()
    # nesting preserved; only the ruled leaves survive (no `secret`, no `junk`)
    assert v.validated() == {"user": {"email": "ada@example.com", "name": "Ada"}}


def test_validated_includes_present_none_for_nullable() -> None:
    data = {"nickname": None, "name": "Ada"}
    v = Validator(data, {"nickname": "nullable", "name": "required"})
    assert not v.fails()
    assert v.validated() == {"nickname": None, "name": "Ada"}  # present-but-None is kept


def test_validated_omits_absent_sometimes_field() -> None:
    data = {"name": "Ada"}
    v = Validator(data, {"name": "required", "nickname": "sometimes|string"})
    assert not v.fails()
    assert v.validated() == {"name": "Ada"}  # absent `sometimes` field never appears


def test_validated_rebuilds_wildcard_array_leaves() -> None:
    data = {"items": [{"price": 10, "sku": "a"}, {"price": 20, "sku": "b"}], "junk": 1}
    v = Validator(data, {"items.*.price": "required|numeric"})
    assert not v.fails()
    # each validated leaf back in its array position; unvalidated `sku`/`junk` excluded
    assert v.validated() == {"items": [{"price": 10}, {"price": 20}]}
