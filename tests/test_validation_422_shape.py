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
