"""Support (doc 06) — C1 residual helpers: optional, throw_unless, Str.random. Test-first."""

from __future__ import annotations

import pytest

from arvel.support import Str, optional, throw_unless


# --- optional() -----------------------------------------------------------------
class _User:
    name = "Ada"


def test_optional_proxies_attributes_when_present() -> None:
    assert optional(_User()).name == "Ada"


def test_optional_returns_none_for_attrs_on_none() -> None:
    assert optional(None).name is None
    assert optional(None).anything_at_all is None


def test_optional_item_access() -> None:
    assert optional({"k": 1})["k"] == 1
    assert optional(None)["k"] is None
    assert optional({"k": 1})["missing"] is None


def test_optional_is_falsy_when_wrapping_none() -> None:
    assert not optional(None)
    assert optional(_User())


# --- throw_unless() (inverse of throw_if) ----------------------------------------
def test_throw_unless_raises_when_falsy() -> None:
    with pytest.raises(ValueError):
        throw_unless(False, ValueError)
    with pytest.raises(RuntimeError):
        throw_unless(0, RuntimeError("boom"))


def test_throw_unless_passes_through_when_truthy() -> None:
    assert throw_unless(True, ValueError) is True
    assert throw_unless("x", ValueError) == "x"


# --- Str.random() ---------------------------------------------------------------
def test_str_random_length_and_alphabet() -> None:
    s = Str.random(24)
    assert len(s) == 24
    assert s.isalnum()


def test_str_random_is_not_deterministic() -> None:
    assert Str.random(32) != Str.random(32)  # cryptographically random, not cached
