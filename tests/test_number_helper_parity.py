"""Number-helper parity (Laravel Number): abbreviate / for_humans / ordinal / file_size / clamp / trim
were absent (the helper had only format/currency/percentage/human). Completes the support-helper family."""

from __future__ import annotations

from arvel.support.number import Number


def test_abbreviate() -> None:
    assert Number.abbreviate(1500) == "1.5K"
    assert Number.abbreviate(2_000_000) == "2M"
    assert Number.abbreviate(999) == "999"


def test_for_humans() -> None:
    assert Number.for_humans(1500) == "1.5 thousand"
    assert Number.for_humans(2_500_000) == "2.5 million"
    assert Number.for_humans(1_000_000_000) == "1 billion"
    assert Number.for_humans(999) == "999"


def test_ordinal() -> None:
    assert [Number.ordinal(n) for n in (1, 2, 3, 4)] == ["1st", "2nd", "3rd", "4th"]
    # the 11/12/13 special case
    assert [Number.ordinal(n) for n in (11, 12, 13)] == ["11th", "12th", "13th"]
    assert [Number.ordinal(n) for n in (21, 22, 23, 113)] == ["21st", "22nd", "23rd", "113th"]


def test_file_size() -> None:
    assert Number.file_size(500) == "500 B"
    assert Number.file_size(1024) == "1 KB"
    assert Number.file_size(1536, 2) == "1.50 KB"
    assert Number.file_size(1024**3) == "1 GB"


def test_clamp() -> None:
    assert Number.clamp(5, 1, 10) == 5
    assert Number.clamp(-3, 1, 10) == 1
    assert Number.clamp(99, 1, 10) == 10


def test_trim() -> None:
    assert Number.trim(12.0) == 12
    assert Number.trim(12.30) == 12.3


def test_format_honors_the_active_locale() -> None:
    """i18n: Number formatting with no locale arg follows the active locale; explicit overrides."""
    from arvel.localization import current_locale

    assert Number.format(1234567.5) == "1,234,567.5"  # default en
    token = current_locale.set("fr_FR")
    try:
        assert Number.format(1234567.5) != "1,234,567.5"  # French grouping differs
        assert Number.currency(19.99, "EUR") != "€19.99"
        assert Number.format(1234567.5, "en_US") == "1,234,567.5"  # explicit overrides
    finally:
        current_locale.reset(token)
