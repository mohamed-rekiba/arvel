"""Custom Rule / Enum objects run on the sync validation path too (round H6).

Regression for a silent-skip hole: a FormRequest declaring a Rule/Enum in rules() used to pass
those fields unchecked on the sync parse() path.
"""

from __future__ import annotations

import enum
from typing import Any

import pytest

from arvel.validation import Enum, FormRequest, Rule, ValidationException, Validator


class Uppercase(Rule):
    message = "The :attribute must be uppercase."

    def passes(self, attribute: str, value: Any) -> bool:
        return isinstance(value, str) and value.isupper()


class Color(enum.Enum):
    RED = "red"
    GREEN = "green"


def test_validator_sync_runs_custom_rule() -> None:
    v = Validator({"code": "abc"}, {"code": [Uppercase()]})
    assert v.fails()
    assert "code" in v.errors()


def test_validator_sync_runs_enum_rule() -> None:
    assert Validator({"c": "purple"}, {"c": [Enum(Color)]}).fails()
    assert Validator({"c": "red"}, {"c": [Enum(Color)]}).passes()


class Signup(FormRequest):
    code: str

    @classmethod
    def rules(cls) -> dict[str, str | list[Any]]:
        return {"code": [Uppercase()]}


def test_formrequest_parse_enforces_custom_rule_on_sync_path() -> None:
    # the hole: this used to silently pass
    with pytest.raises(ValidationException):
        Signup.parse({"code": "lower"})
    ok = Signup.parse({"code": "UPPER"})
    assert ok.code == "UPPER"


def test_bail_stops_at_first_failure_including_rule_objects() -> None:
    v = Validator({"code": "abc"}, {"code": ["bail", Uppercase(), "min:99"]})
    v.fails()
    # bail: only the first failing rule (Uppercase) recorded, not min:99 too
    assert len(v.errors()["code"]) == 1


@pytest.mark.asyncio
async def test_async_path_runs_rule_once_no_double_error() -> None:
    v = Validator({"code": "abc"}, {"code": [Uppercase()]})
    await v.passes_async()
    assert len(v.errors()["code"]) == 1  # not doubled by sync+async both running it
