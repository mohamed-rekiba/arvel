"""Both validation engines must reject with one contract: field-keyed
{field: [messages]}, nested paths in dot syntax."""

from __future__ import annotations

import msgspec
import pytest

from arvel.validation import ValidationException, validate


class Item(msgspec.Struct):
    name: str
    qty: int


class Order(msgspec.Struct):
    email: str
    items: list[Item]


def _errors(fn: object) -> dict[str, list[str]]:
    with pytest.raises(ValidationException) as exc_info:
        fn()  # type: ignore[operator]  # test helper takes a thunk
    errors = exc_info.value.errors
    assert isinstance(errors, dict), f"422 errors must be field-keyed, got {type(errors)}"
    return errors


def test_wrong_type_is_keyed_by_field() -> None:
    errors = _errors(
        lambda: validate({"email": "e", "items": [{"name": "x", "qty": "NaN"}]}, Order, strict=True)
    )
    assert list(errors.keys()) == ["items.0.qty"]
    assert isinstance(errors["items.0.qty"], list) and errors["items.0.qty"]


def test_missing_field_is_keyed_by_field() -> None:
    errors = _errors(lambda: validate({"items": []}, Order))
    assert "email" in errors


def test_root_level_failure_gets_stable_body_key() -> None:
    errors = _errors(lambda: validate({"email": "e", "items": "not-a-list"}, Order))
    assert len(errors) == 1  # keyed by items-path or _body, never a bare string


class Three(msgspec.Struct):
    a: int
    b: str
    c: bool


def test_three_bad_fields_yield_a_three_key_error_map() -> None:
    # msgspec's whole-struct convert is fail-fast (first bad field only) — H9 aggregates all of them.
    errors = _errors(lambda: validate({"a": "x", "b": 1, "c": "nah"}, Three, strict=True))
    assert len(errors) == 3
    assert set(errors) == {"a", "b", "c"}


def test_single_bad_field_still_yields_a_one_key_map() -> None:
    errors = _errors(lambda: validate({"a": "x", "b": "ok", "c": True}, Three, strict=True))
    assert len(errors) == 1
    assert set(errors) == {"a"}


def test_valid_body_still_constructs_via_the_unchanged_happy_path() -> None:
    instance = validate({"a": 1, "b": "ok", "c": True}, Three, strict=True)
    assert instance == Three(a=1, b="ok", c=True)


class Renamed(msgspec.Struct, rename={"user_name": "userName", "zip_code": "zipCode"}):
    user_name: str
    zip_code: int


def test_renamed_fields_aggregate_under_their_wire_names() -> None:
    # a renamed field must report under the name the client actually sent (the wire name),
    # so the error map keys line up with the request body — both bad fields, both keyed by wire name
    errors = _errors(lambda: validate({"userName": 5, "zipCode": "nope"}, Renamed))
    assert set(errors) == {"userName", "zipCode"}
