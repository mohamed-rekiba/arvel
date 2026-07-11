"""ORM depth (doc 07) — Attribute accessors/mutators, appends, custom casts. Test-first."""

from __future__ import annotations

from typing import Any

from arvel.database import Attribute, Model


class Account(Model):
    __fields__ = {"first_name": str, "last_name": str, "email": str}
    __fillable__ = ["first_name", "last_name", "email"]
    __appends__ = ["full_name"]

    def email(self) -> Attribute:
        return Attribute(get=lambda v, a: v.lower(), set=lambda v, a: v.strip().lower())

    def full_name(self) -> Attribute:
        return Attribute(get=lambda v, a: f"{a['first_name']} {a['last_name']}", cached=True)


def test_repr_shows_stored_attributes() -> None:
    account = Account()
    account.fill({"first_name": "Ada", "email": "a@b.com"})
    # column values, not the bare "<Account object at 0x...>" — usable at the REPL / under dump
    assert repr(account) == "Account(first_name='Ada', email='a@b.com')"
    assert repr(Account()) == "Account()"  # no attributes yet


def test_mutator_applies_on_set() -> None:
    account = Account()
    account.fill({"email": "  Ada@X.COM "})
    assert account._attributes["email"] == "ada@x.com"  # mutator: strip + lower


def test_accessor_applies_on_get() -> None:
    account = Account()
    account._attributes["email"] = "ADA@x.COM"  # raw, bypassing the mutator
    assert account.email == "ada@x.com"  # accessor lowercases (method did not shadow)


def test_appends_computed_attribute_in_to_dict() -> None:
    account = Account()
    account.fill({"first_name": "Ada", "last_name": "Lovelace", "email": "a@b.com"})
    data = account.to_dict()
    assert data["full_name"] == "Ada Lovelace"


def test_cached_accessor_computes_once() -> None:
    calls = {"n": 0}

    class Widget(Model):
        __fields__ = {"raw": str}
        __fillable__ = ["raw"]

        def label(self) -> Attribute:
            def compute(value: Any, attrs: Any) -> str:
                calls["n"] += 1
                return f"#{attrs['raw']}"

            return Attribute(get=compute, cached=True)

    widget = Widget()
    widget.fill({"raw": "x"})
    assert widget.label == "#x"
    assert widget.label == "#x"
    assert calls["n"] == 1  # cached


def test_custom_cast_protocol() -> None:
    class UpperCast:
        def get(self, model: Any, key: str, value: Any, attrs: Any) -> Any:
            return value.upper()

        def set(self, model: Any, key: str, value: Any, attrs: Any) -> Any:
            return value.lower()

    class Code(Model):
        __fields__ = {"sku": str}
        __fillable__ = ["sku"]
        __casts__ = {"sku": UpperCast()}

    code = Code()
    code.fill({"sku": "AbC"})
    assert code._attributes["sku"] == "abc"  # cast.set lowercases
    assert code.sku == "ABC"  # cast.get uppercases
