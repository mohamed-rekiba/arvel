"""Story-08 review blocker: to_dict/to_json of collection/object/stringable/decimal casts
must emit JSON-native values, not str(Collection(...)) garbage."""

from __future__ import annotations

import json
from typing import ClassVar

import sqlalchemy as sa

from arvel.database.model import Model


class Doc(Model):
    __table__ = sa.Table(
        "docs",
        sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tags", sa.Text),
        sa.Column("profile", sa.Text),
        sa.Column("slug", sa.Text),
        sa.Column("price", sa.Text),
    )
    __fillable__: ClassVar = ["tags", "profile", "slug", "price"]
    __casts__: ClassVar = {
        "tags": "collection",
        "profile": "object",
        "slug": "stringable",
        "price": "decimal:2",
    }


def test_to_dict_unwraps_cast_wrappers_to_native() -> None:
    doc = Doc(tags=[1, 2, 3], profile={"name": "Ada"}, slug="Hello World", price="9.999")
    data = doc.to_dict()
    assert data["tags"] == [1, 2, 3]  # Collection -> list
    assert data["profile"] == {"name": "Ada"}  # SimpleNamespace -> dict
    assert data["slug"] == "Hello World"  # Stringable -> str
    assert data["price"] == "10.00"  # Decimal -> quantized str


def test_to_json_roundtrips_without_repr_garbage() -> None:
    doc = Doc(tags=[1, 2], profile={"x": 1}, slug="s", price="1.5")
    loaded = json.loads(doc.to_json())
    assert loaded["tags"] == [1, 2]
    assert loaded["profile"] == {"x": 1}
    assert "Collection(" not in doc.to_json()
    assert "namespace(" not in doc.to_json()


def _demo() -> None:
    d = Doc(tags=["a"], profile={"k": "v"}, slug="z", price="2.005")
    out = d.to_dict()
    assert isinstance(out["tags"], list) and isinstance(out["profile"], dict), out
    assert isinstance(out["price"], str), out


if __name__ == "__main__":
    _demo()
    print("ok")
