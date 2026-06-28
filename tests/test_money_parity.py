"""Money value object (moneyphp parity): immutable integer-minor-unit amounts + Currency, arithmetic
with a same-currency guard, penny-perfect allocate, comparison, predicates, and locale-aware formatting."""

from __future__ import annotations

import random
from decimal import Decimal

import pytest

from arvel.support import Currency, Money


def test_construction_and_accessors() -> None:
    assert Money.of("19.99", "USD").amount == 1999  # major → minor
    assert Money.of(1500, "JPY").amount == 1500  # JPY has 0 minor units
    assert Money(1999, "USD").major() == Decimal("19.99")
    assert Money(1999, "USD").currency == Currency("usd")  # case-insensitive code


def test_arithmetic_and_currency_guard() -> None:
    assert (Money(1999, "USD") + Money(1, "USD")).amount == 2000
    assert (Money(500, "USD") - Money(200, "USD")).amount == 300
    assert Money.of("19.99", "USD").times(3).amount == 5997
    assert Money(100, "USD").times("1.005").amount == 101  # half-up rounding
    assert (-Money(5, "USD")).amount == -5
    assert Money(-5, "USD").absolute().amount == 5
    with pytest.raises(ValueError):
        Money(1, "USD") + Money(1, "EUR")


def test_allocate_is_penny_perfect() -> None:
    assert [m.amount for m in Money(1000, "USD").allocate([1, 1, 1])] == [334, 333, 333]
    assert [m.amount for m in Money(1005, "USD").allocate([3, 7])] == [302, 703]
    assert [m.amount for m in Money(10, "USD").allocate_to(3)] == [4, 3, 3]
    with pytest.raises(ValueError):
        Money(10, "USD").allocate([0, 0])  # sum must be > 0
    with pytest.raises(ValueError):
        Money(10, "USD").allocate([1, -1])  # no negative ratios


def test_allocate_never_loses_a_unit() -> None:
    rng = random.Random(42)
    for _ in range(1000):
        amount = rng.randint(-9999, 9999)
        ratios = [rng.randint(0, 9) for _ in range(rng.randint(1, 7))]
        if sum(ratios) <= 0:
            ratios = [1]
        shares = Money(amount, "USD").allocate(ratios)
        assert sum(m.amount for m in shares) == amount  # invariant: no minor unit lost


def test_comparison_and_predicates() -> None:
    assert Money(5, "USD").compare(Money(3, "USD")) == 1
    assert Money(5, "USD") > Money(3, "USD")
    assert Money(3, "USD") <= Money(3, "USD")
    assert Money(5, "USD").equals(Money(5, "USD"))
    assert not Money(5, "USD").equals(Money(5, "EUR"))  # different currency
    assert Money(0, "USD").is_zero()
    assert Money(1, "USD").is_positive() and Money(-1, "USD").is_negative()
    with pytest.raises(ValueError):
        Money(1, "USD").compare(Money(1, "EUR"))


def test_formatting() -> None:
    assert Money.of("19.99", "USD").format("en_US") == "$19.99"
    assert Money(1500, "JPY").format("en_US") == "¥1,500"
    assert str(Money.of("5", "USD")) == Money.of("5", "USD").format()


def test_format_honors_the_active_locale() -> None:
    """i18n: format() with no arg follows the active locale; explicit locale overrides."""
    from arvel.localization import current_locale

    token = current_locale.set("fr_FR")
    try:
        fr = Money.of("1234.5", "EUR").format()
        # French: comma decimal + trailing euro, differs from the en default.
        # Exact whitespace (narrow/no-break spaces) varies by CLDR version — assert shape.
        assert ",50" in fr and "€" in fr and fr != "€1,234.50"
        assert Money.of("1234.5", "USD").format("en_US") == "$1,234.50"  # explicit wins
    finally:
        current_locale.reset(token)
    assert Money.of("1234.5", "USD").format() == "$1,234.50"  # back to the default (en)


def test_immutable_and_hashable() -> None:
    m = Money(100, "USD")
    assert m.plus(Money(1, "USD")).amount == 101 and m.amount == 100  # original unchanged
    assert {Money(1, "USD"), Money(1, "USD"), Money(2, "USD")} == {Money(1, "USD"), Money(2, "USD")}
