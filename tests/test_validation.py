"""T4.5 — validation on msgspec: validate(), json_schema(), FormRequest."""

from __future__ import annotations

import msgspec
import pytest

from arvel.validation import FormRequest, ValidationException, json_schema, validate


class StoreUser(msgspec.Struct):
    name: str
    age: int


def test_validate_ok() -> None:
    obj = validate({"name": "ada", "age": 36}, StoreUser)
    assert obj == StoreUser(name="ada", age=36)


def test_validate_coerces() -> None:
    obj = validate({"name": "ada", "age": "36"}, StoreUser)  # str → int
    assert obj.age == 36


def test_validate_missing_field_raises_422() -> None:
    with pytest.raises(ValidationException) as exc:
        validate({"name": "ada"}, StoreUser)
    assert exc.value.status == 422


def test_json_schema_has_properties() -> None:
    schema = json_schema(StoreUser)
    props = next(iter(schema["$defs"].values()))["properties"]
    assert set(props) == {"name", "age"}


class RegisterRequest(FormRequest):
    email: str
    password: str


def test_form_request_parse_and_authorize() -> None:
    req = RegisterRequest.parse({"email": "a@b.c", "password": "secret"})
    assert req.email == "a@b.c"
    assert req.authorize() is True


def test_form_request_invalid() -> None:
    with pytest.raises(ValidationException):
        RegisterRequest.parse({"email": "a@b.c"})
