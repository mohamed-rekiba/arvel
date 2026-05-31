"""WI-arvel-019 — Epic 006 Story 5: unified ``Attribute``-style accessor/mutator.

A single descriptor defines symmetric ``get``/``set`` under one attribute name,
backed by one or more real columns, with opt-in per-instance caching.
"""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database import Attribute, Model, id_, integer, string


def _split_name(_model: Any, value: str) -> dict[str, str]:
    first, _, last = value.partition(" ")
    return {"first_name": first, "last_name": last}


class _Person(Model):
    __tablename__ = "wi019_people"
    id: int = id_()
    first_name: str = string(50, default="")
    last_name: str = string(50, default="")

    full_name = Attribute.make(
        get=lambda m: f"{m.first_name} {m.last_name}".strip(),
        set=_split_name,
    )

    upper_first = Attribute.make(get=lambda m: m.first_name.upper())
    write_only = Attribute.make(set=lambda _m, v: {"last_name": v})


class _Counter(Model):
    __tablename__ = "wi019_counters"
    id: int = id_()
    base: int = integer(default=0)

    doubled = Attribute.make(
        get=lambda m: m.base * 2,
        set=lambda _m, v: {"base": v // 2},
    ).should_cache()


class TestUnifiedReadWrite:
    def test_get_computes_from_columns(self) -> None:
        p = _Person(first_name="Ada", last_name="Lovelace")
        assert p.full_name == "Ada Lovelace"

    def test_set_writes_through_to_columns(self) -> None:
        p = _Person(first_name="x", last_name="y")
        p.full_name = "Grace Hopper"
        assert p.first_name == "Grace"
        assert p.last_name == "Hopper"
        assert p.full_name == "Grace Hopper"

    def test_read_only_attribute_rejects_write(self) -> None:
        p = _Person(first_name="Ada", last_name="L")
        assert p.upper_first == "ADA"
        with pytest.raises(AttributeError, match="read-only"):
            p.upper_first = "nope"

    def test_write_only_attribute_rejects_read(self) -> None:
        p = _Person()
        p.write_only = "Curie"
        assert p.last_name == "Curie"
        with pytest.raises(AttributeError, match="write-only"):
            _ = p.write_only

    def test_non_mapping_setter_raises(self) -> None:
        class _Bad(Model):
            __tablename__ = "wi019_bad"
            id: int = id_()
            name: str = string(50, default="")
            virt = Attribute.make(get=lambda m: m.name, set=lambda _m, v: v)

        b = _Bad()
        with pytest.raises(TypeError, match="mapping of column"):
            b.virt = "boom"

    def test_class_access_returns_descriptor(self) -> None:
        assert isinstance(_Person.__dict__["full_name"], Attribute)


class TestCaching:
    def test_value_is_cached_per_instance(self) -> None:
        c = _Counter(base=5)
        assert c.doubled == 10
        # Mutate the backing column directly — cache is intentionally sticky.
        object.__setattr__(c, "base", 50)
        assert c.doubled == 10

    def test_set_invalidates_cache(self) -> None:
        c = _Counter(base=5)
        assert c.doubled == 10
        c.doubled = 40
        assert c.base == 20
        assert c.doubled == 40

    def test_cache_is_independent_across_instances(self) -> None:
        a = _Counter(base=1)
        b = _Counter(base=3)
        assert a.doubled == 2
        assert b.doubled == 6
