"""Validation (doc 10) — custom rule objects (class X(Rule): def passes)."""

from __future__ import annotations

from typing import Any

from arvel.validation import Rule, ValidationException, Validator


class Uppercase(Rule):
    message = "The :attribute must be uppercase."

    def passes(self, attribute: str, value: Any) -> bool:
        return isinstance(value, str) and value.isupper()


async def test_custom_rule_passes() -> None:
    v = Validator({"code": "ABC"}, {"code": [Uppercase()]})
    assert await v.passes_async() is True


async def test_custom_rule_fails_with_message() -> None:
    v = Validator({"code": "abc"}, {"code": [Uppercase()]})
    assert await v.fails_async() is True
    assert v.errors()["code"] == ["The code must be uppercase."]


async def test_custom_rule_mixes_with_string_rules() -> None:
    # required (string rule) + Uppercase (object): both enforced
    v = Validator({"code": "abc"}, {"code": ["required", Uppercase()]})
    assert await v.fails_async() is True
    assert "The code must be uppercase." in v.errors()["code"]

    v2 = Validator({}, {"code": ["required", Uppercase()]})
    assert await v2.fails_async() is True
    assert any("required" in m for m in v2.errors()["code"])


async def test_custom_rule_raises_on_validate_async() -> None:
    v = Validator({"code": "abc"}, {"code": [Uppercase()]})
    raised = False
    try:
        await v.validate_async()
    except ValidationException:
        raised = True
    assert raised


class _AlwaysFail(Rule):
    message = "The :attribute custom failed."

    def passes(self, attribute: str, value: object) -> bool:
        return False


def test_errors_runs_validation_lazily() -> None:
    """The docs' standalone one-liner: errors() on a fresh validator returns the populated bag —
    it must trigger the (sync) pass itself, not silently return {}."""
    errors = Validator({"x": ""}, {"x": "bail|required|email"}).errors()
    assert errors == {"x": ["The x field is required."]}


def test_validated_standalone_honors_exclusions() -> None:
    """validated() called before any explicit pass must still drop exclude_if fields — the
    allow-list promise holds without requiring the caller to run validate() first."""
    v = Validator(
        {"type": "cash", "card": "4111", "amount": "10"},
        {"type": "required", "card": "exclude_if:type,cash", "amount": "required"},
    )
    assert v.validated() == {"type": "cash", "amount": "10"}  # card excluded, not leaked


async def test_bail_holds_on_the_async_path() -> None:
    """`bail` = one error per field, on BOTH paths: a field that already failed a sync rule must
    not collect a second error from its deferred custom (or DB) rule in passes_async."""
    data = {"code": "nope"}
    rules = {"code": ["bail", "email", _AlwaysFail()]}

    sync_v = Validator(data, dict(rules))
    sync_v.passes()
    async_v = Validator(data, dict(rules))
    await async_v.passes_async()

    assert sync_v.errors() == async_v.errors()
    assert async_v.errors() == {"code": ["The code must be a valid email address."]}
