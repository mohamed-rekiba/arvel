"""Coverage — Model mass-assignment / __setattr__ / enum-cast branch paths (doc 07)."""

from __future__ import annotations

import enum
from typing import ClassVar

from arvel.database import Model


class Color(enum.Enum):
    RED = "red"


class Whitelisted(Model):
    __fields__: ClassVar = {"a": str, "b": str, "c": str}
    __fillable__: ClassVar = ["a", "c"]  # whitelist: 'a' + 'c' ('b' excluded)
    __casts__: ClassVar = {"c": Color}


class Unguarded(Model):
    __fields__: ClassVar = {"a": str}
    __guarded__: ClassVar = []  # nothing guarded → everything fillable


def test_fillable_whitelist_blocks_others() -> None:
    m = Whitelisted()
    m.fill({"a": "x", "b": "y"})
    assert m._attributes.get("a") == "x"
    assert "b" not in m._attributes  # not in __fillable__ → blocked


def test_unguarded_allows_all() -> None:
    m = Unguarded()
    m.fill({"a": "x"})
    assert m._attributes["a"] == "x"


def test_setattr_branches() -> None:
    m = Whitelisted()
    m._private = 1  # underscore → object.__setattr__
    assert m._private == 1
    m.a = "v"  # plain attribute → cast into _attributes
    assert m._attributes["a"] == "v"


def test_enum_cast_set_branch() -> None:
    m = Whitelisted()
    m.fill({"c": Color.RED})
    assert m._attributes["c"] == "red"  # Enum instance → .value on set
