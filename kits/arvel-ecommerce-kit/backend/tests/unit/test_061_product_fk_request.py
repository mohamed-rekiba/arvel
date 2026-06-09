"""validate_product_fks: coercion, normalization, and Rule.exists delegation."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from app.http.requests import product_request
from app.http.requests.product_request import validate_product_fks
from arvel.http.exceptions import ValidationException


class _FakeValidator:
    """Stand-in for arvel.validation.Validator that records the rules it got."""

    last_data: Any = None
    last_rules: Any = None

    def __init__(self, data: Any) -> None:
        _FakeValidator.last_data = data

    async def validate(self, rules: Any) -> list[dict[str, str]]:
        _FakeValidator.last_rules = rules
        return []


@pytest.fixture(autouse=True)
def _stub_validator(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeValidator.last_data = None
    _FakeValidator.last_rules = None
    monkeypatch.setattr(product_request, "Validator", _FakeValidator)


@pytest.mark.asyncio
async def test_blank_fk_normalizes_to_none_without_db() -> None:
    data: dict[str, Any] = {"category_id": "", "vendor_id": ""}
    await validate_product_fks(data)
    assert data == {"category_id": None, "vendor_id": None}
    # No truthy FK → no exists rule → Validator never consulted.
    assert _FakeValidator.last_rules is None


@pytest.mark.asyncio
async def test_absent_fk_is_left_untouched() -> None:
    data: dict[str, Any] = {"name": {"en": "x"}}
    await validate_product_fks(data)
    assert data == {"name": {"en": "x"}}


@pytest.mark.asyncio
async def test_malformed_uuid_raises_validation_error() -> None:
    with pytest.raises(ValidationException):
        await validate_product_fks({"category_id": "not-a-uuid"})


@pytest.mark.asyncio
async def test_valid_fk_coerced_and_exists_rule_built() -> None:
    cat = uuid.uuid4()
    ven = uuid.uuid4()
    data: dict[str, Any] = {"category_id": str(cat), "vendor_id": str(ven)}
    await validate_product_fks(data)
    # Coerced to real UUIDs so Rule.exists binds against the uuid PK column.
    assert data["category_id"] == cat
    assert data["vendor_id"] == ven
    assert _FakeValidator.last_rules == {
        "category_id": "exists:categories,id",
        "vendor_id": "exists:vendors,id",
    }
