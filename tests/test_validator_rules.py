"""Coverage — the full rule set + FormRequest (doc 10)."""

from __future__ import annotations

import pytest

from arvel.validation import FormRequest, ValidationException, Validator


def test_type_rules() -> None:
    assert Validator({"n": 5}, {"n": "integer"}).passes()
    assert Validator({"n": "5"}, {"n": "integer"}).passes()
    assert Validator({"n": "x"}, {"n": "integer"}).fails()
    assert Validator({"n": 3.5}, {"n": "numeric"}).passes()
    assert Validator({"n": "3.5"}, {"n": "numeric"}).passes()
    assert Validator({"n": "x"}, {"n": "numeric"}).fails()
    assert Validator({"b": True}, {"b": "boolean"}).passes()
    assert Validator({"s": "abc"}, {"s": "string"}).passes()


def test_string_format_rules() -> None:
    assert Validator({"s": "abc"}, {"s": "alpha"}).passes()
    assert Validator({"s": "a1"}, {"s": "alpha"}).fails()
    assert Validator({"s": "a1"}, {"s": "alpha_num"}).passes()
    assert Validator({"u": "https://x.com"}, {"u": "url"}).passes()
    assert Validator({"u": "nope"}, {"u": "url"}).fails()
    assert Validator({"s": "abc123"}, {"s": r"regex:^[a-z0-9]+$"}).passes()


def test_in_same_different_accepted() -> None:
    assert Validator({"r": "admin"}, {"r": "in:admin,user"}).passes()
    assert Validator({"r": "ghost"}, {"r": "in:admin,user"}).fails()
    assert Validator({"a": 1, "b": 1}, {"a": "same:b"}).passes()
    assert Validator({"a": 1, "b": 2}, {"a": "same:b"}).fails()
    assert Validator({"a": 1, "b": 2}, {"a": "different:b"}).passes()
    assert Validator({"tos": "yes"}, {"tos": "accepted"}).passes()
    assert Validator({"tos": "no"}, {"tos": "accepted"}).fails()


def test_min_max_numeric_and_length() -> None:
    assert Validator({"n": 20}, {"n": "numeric|min:18|max:65"}).passes()
    assert Validator({"n": 10}, {"n": "numeric|min:18"}).fails()
    assert Validator({"s": "abcd"}, {"s": "max:3"}).fails()
    assert Validator({"s": "ab"}, {"s": "min:2"}).passes()
    assert Validator({"flag": True}, {"flag": "min:1"}).passes()  # bool size


def test_custom_message_per_rule_and_field() -> None:
    v = Validator({}, {"email": "required"}, {"required": "is required!"})
    v.passes()
    assert v.errors()["email"] == ["is required!"]


def test_validated_subset() -> None:
    v = Validator({"a": 1, "b": 2, "extra": 9}, {"a": "integer", "b": "integer"})
    assert v.passes()
    assert v.validated() == {"a": 1, "b": 2}


class CreateUser(FormRequest):
    name: str

    def authorize(self) -> bool:
        return True


def test_form_request_parse() -> None:
    dto = CreateUser.parse({"name": "ada"})
    assert dto.name == "ada"
    assert dto.authorize() is True
    with pytest.raises(ValidationException):
        CreateUser.parse({})  # missing required field
