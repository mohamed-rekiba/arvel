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
