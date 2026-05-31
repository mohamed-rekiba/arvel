"""Eloquent-parity (backlog 006, S1): attribute-level custom cast protocol."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, ClassVar

import pytest
from arvel.database import CastsAttributes, Model, column, id_
from sqlalchemy import Integer, Numeric, String
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class AsJson(CastsAttributes):
    def get(self, model: Any, key: str, value: Any) -> dict[str, Any]:
        parsed: dict[str, Any] = json.loads(value) if isinstance(value, str) else value
        return parsed

    def set(self, model: Any, key: str, value: Any) -> Any:
        return value if isinstance(value, str) else json.dumps(value)

    def serialize(self, model: Any, key: str, value: Any) -> Any:
        return value


class AsUpper(CastsAttributes):
    def get(self, model: Any, key: str, value: Any) -> str:
        return str(value).upper()

    def set(self, model: Any, key: str, value: Any) -> Any:
        return value


class Doc(Model):
    __tablename__ = "cast_docs"
    __casts__: ClassVar[dict[str, Any]] = {
        "meta": AsJson,  # class form
        "code": AsUpper(),  # instance form
        "price": "decimal:2",  # parameterized built-in
        "flag": "boolean",  # plain built-in still works
    }

    id: int = id_()
    # Cast-backed columns accept/return types wider than their storage type → Any.
    meta: Any = column(String(500), default="{}")
    code: Any = column(String(50), default="")
    price: Any = column(Numeric(10, 2), default=Decimal(0))
    flag: Any = column(Integer, default=0)


async def _create_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


def test_custom_cast_class_routes_get_and_set() -> None:
    doc = Doc(meta={"a": 1})
    # set() JSON-encoded it for storage; get() parses back to a dict.
    assert doc.meta == {"a": 1}


def test_custom_cast_instance_form() -> None:
    doc = Doc(code="abc")
    assert doc.code == "ABC"


def test_parameterized_decimal_cast_quantizes() -> None:
    doc = Doc(price="10.005")
    assert doc.price == Decimal("10.01")  # ROUND_HALF_UP at scale 2


def test_plain_builtin_cast_still_works() -> None:
    # Separate instances so mypy doesn't narrow `flag` to the assigned str literal.
    assert Doc(flag="0").flag is False
    assert Doc(flag="1").flag is True


def test_to_dict_uses_cast_serialize() -> None:
    doc = Doc(meta={"x": [1, 2]}, code="hi")
    data = doc.to_dict()
    # serialize() yields the dict, not the stored JSON string.
    assert data["meta"] == {"x": [1, 2]}


async def test_custom_cast_roundtrips_through_db(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _create_tables(engine)
    doc = Doc(meta={"k": "v"}, code="abc", price="3.5", flag="1")
    await doc.save()
    fresh = await Doc.query().first()
    assert fresh is not None
    assert fresh.meta == {"k": "v"}
    assert fresh.code == "ABC"
    assert fresh.price == Decimal("3.50")
    assert fresh.flag is True


def _define_model_with_casts(table: str, casts: dict[str, Any]) -> type[Model]:
    """Build a minimal Model subclass so cast validation runs in __init_subclass__."""
    return type(
        table,
        (Model,),
        {
            "__tablename__": table,
            "__casts__": casts,
            "__annotations__": {"id": int},
            "id": id_(),
        },
    )


def test_unknown_string_cast_raises_at_definition() -> None:
    with pytest.raises(ValueError, match="not a recognised cast type"):
        _define_model_with_casts("cast_bad1", {"x": "nonsense"})


def test_non_spec_value_raises_type_error() -> None:
    with pytest.raises(TypeError, match="cast spec must be a str"):
        _define_model_with_casts("cast_bad2", {"x": 123})
