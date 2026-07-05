"""New cast round-trips (spec 08 §3
``immutable_datetime`` — arvel's ``datetime`` cast already returns the immutable ``Date``):
``array``/``json``/``collection``/``object``/``decimal:<scale>``/``encrypted:array``/
``encrypted:json``/``stringable``, each round-tripped write→read on SQLite."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import ClassVar

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model
from arvel.kernel import Application, set_application
from arvel.security import Encrypter
from arvel.support import Collection, Stringable


class Item(Model):
    __fields__: ClassVar = {
        "tags": list,
        "meta": dict,
        "extra": dict,
        "profile": dict,
        "price": str,
        "secret_list": str,
        "secret_map": str,
        "slug": str,
    }
    __fillable__: ClassVar = list(__fields__)
    __casts__: ClassVar = {
        "tags": "array",
        "meta": "json",
        "extra": "collection",
        "profile": "object",
        "price": "decimal:2",
        "secret_list": "encrypted:array",
        "secret_map": "encrypted:json",
        "slug": "stringable",
    }


async def _setup() -> ConnectionResolver:
    app = Application()
    app.instance("encrypter", Encrypter(Encrypter.generate_key()))
    set_application(app)
    db = ConnectionResolver()
    Item.set_connection(db)
    await db.execute(sa.schema.CreateTable(Item.__table__))
    return db


async def test_array_cast_round_trips_a_list() -> None:
    db = await _setup()
    try:
        created = await Item.create(tags=["a", "b"], meta={}, extra=[], profile={}, price="1")
        assert isinstance(created._attributes["tags"], str)  # stored as JSON text
        reloaded = await Item.find(created.id)
        assert reloaded is not None
        assert reloaded.tags == ["a", "b"]
    finally:
        set_application(None)
        await db.dispose()


async def test_json_cast_round_trips_a_dict() -> None:
    db = await _setup()
    try:
        created = await Item.create(tags=[], meta={"k": "v"}, extra=[], profile={}, price="1")
        reloaded = await Item.find(created.id)
        assert reloaded is not None
        assert reloaded.meta == {"k": "v"}
    finally:
        set_application(None)
        await db.dispose()


async def test_collection_cast_round_trips_to_a_collection() -> None:
    db = await _setup()
    try:
        created = await Item.create(
            tags=[], meta={}, extra=Collection([1, 2, 3]), profile={}, price="1"
        )
        reloaded = await Item.find(created.id)
        assert reloaded is not None
        assert isinstance(reloaded.extra, Collection)
        assert reloaded.extra.all() == [1, 2, 3]
    finally:
        set_application(None)
        await db.dispose()


async def test_object_cast_round_trips_to_a_simplenamespace() -> None:
    db = await _setup()
    try:
        created = await Item.create(
            tags=[], meta={}, extra=[], profile={"name": "Ada", "age": 30}, price="1"
        )
        reloaded = await Item.find(created.id)
        assert reloaded is not None
        assert isinstance(reloaded.profile, SimpleNamespace)
        assert reloaded.profile.name == "Ada"
        assert reloaded.profile.age == 30
    finally:
        set_application(None)
        await db.dispose()


async def test_object_cast_serializes_via_vars_on_set() -> None:
    db = await _setup()
    try:
        created = await Item.create(
            tags=[], meta={}, extra=[], profile=SimpleNamespace(x=1), price="1"
        )
        assert isinstance(created._attributes["profile"], str)
        reloaded = await Item.find(created.id)
        assert reloaded is not None and reloaded.profile.x == 1
    finally:
        set_application(None)
        await db.dispose()


async def test_decimal_cast_quantizes_to_the_declared_scale() -> None:
    db = await _setup()
    try:
        created = await Item.create(tags=[], meta={}, extra=[], profile={}, price=Decimal("1.005"))
        assert isinstance(created.price, Decimal)
        assert created.price == Decimal("1.00")  # ROUND_HALF_EVEN quantize to 2dp
        reloaded = await Item.find(created.id)
        assert reloaded is not None
        assert reloaded.price == Decimal("1.00")
        assert isinstance(reloaded.price, Decimal)
    finally:
        set_application(None)
        await db.dispose()


async def test_encrypted_array_round_trips_and_is_unreadable_raw() -> None:
    db = await _setup()
    try:
        created = await Item.create(
            tags=[], meta={}, extra=[], profile={}, price="1", secret_list=[1, 2, "x"]
        )
        raw = created._attributes["secret_list"]
        assert isinstance(raw, str) and raw.startswith("v1.")  # ciphertext envelope, not JSON
        assert raw != '[1, 2, "x"]' and "1, 2" not in raw  # not the plaintext JSON, verbatim
        reloaded = await Item.find(created.id)
        assert reloaded is not None
        assert reloaded.secret_list == [1, 2, "x"]
    finally:
        set_application(None)
        await db.dispose()


async def test_encrypted_json_round_trips_a_dict() -> None:
    db = await _setup()
    try:
        created = await Item.create(
            tags=[], meta={}, extra=[], profile={}, price="1", secret_map={"pin": "1234"}
        )
        raw = created._attributes["secret_map"]
        assert isinstance(raw, str) and raw.startswith("v1.")
        assert '"pin"' not in raw and '"1234"' not in raw  # not the plaintext JSON, verbatim
        reloaded = await Item.find(created.id)
        assert reloaded is not None
        assert reloaded.secret_map == {"pin": "1234"}
    finally:
        set_application(None)
        await db.dispose()


async def test_stringable_cast_returns_a_stringable() -> None:
    db = await _setup()
    try:
        created = await Item.create(tags=[], meta={}, extra=[], profile={}, price="1", slug="hi")
        assert isinstance(created.slug, Stringable)
        assert str(created.slug) == "hi"
        reloaded = await Item.find(created.id)
        assert reloaded is not None
        assert isinstance(reloaded.slug, Stringable)
        assert str(reloaded.slug.upper()) == "HI"
    finally:
        set_application(None)
        await db.dispose()
