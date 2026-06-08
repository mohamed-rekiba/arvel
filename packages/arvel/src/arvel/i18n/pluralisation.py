"""Laravel-pipe pluralisation + bracket-range syntax."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Final

_BRACKET_RANGE: Final[re.Pattern[str]] = re.compile(r"^\[(\d+),(\*|\d+)\](.*)$")
_BRACKET_EXACT: Final[re.Pattern[str]] = re.compile(r"^\{(\d+)\}(.*)$")


def select_plural_variant(
    spec: str,
    *,
    count: int,
    replace: Mapping[str, object],
    locale: str = "en",
) -> str:
    """Pick the right variant for ``count`` and substitute placeholders.

    Two syntaxes interoperate:
    - Positional pipe: ``"apple|apples"``       picked by the locale's plural rule,
                                                not by raw index. English: ``count == 1``
                                                takes the first form, everything else
                                                the second. Use brackets for >2 forms.
    - Bracket: ``"{0}none|[1,4]few|other"``     exact ``{N}`` and range ``[a,b]``.
                                                Open-ended: ``[1,*]``.
                                                Bare-prefix entry = default (last wins).
    """
    variants = spec.split("|")

    # First pass: try bracket-prefixed matches.
    default: str | None = None
    for variant in variants:
        m = _BRACKET_EXACT.match(variant)
        if m and int(m.group(1)) == count:
            return _substitute(m.group(2), count=count, replace=replace)
        m = _BRACKET_RANGE.match(variant)
        if m:
            lo = int(m.group(1))
            hi_str = m.group(2)
            hi = int(hi_str) if hi_str != "*" else None
            if lo <= count and (hi is None or count <= hi):
                return _substitute(m.group(3), count=count, replace=replace)
        # Track the last bare variant as the default for bracket-style specs.
        elif not _BRACKET_EXACT.match(variant) and not _BRACKET_RANGE.match(variant):
            default = variant

    # Second pass: positional fallback.
    # If any variant uses bracket syntax, return the default (no positional fallback).
    has_bracket = any(_BRACKET_EXACT.match(v) or _BRACKET_RANGE.match(v) for v in variants)
    if has_bracket:
        if default is not None:
            return _substitute(default, count=count, replace=replace)
        return _substitute(variants[-1], count=count, replace=replace)

    # Positional: pick the form via the locale's plural rule (Laravel's
    # MessageSelector::getPluralIndex), not by raw count index. So "apple|apples"
    # in English gives the singular only at count == 1.
    idx = _plural_index(locale, count)
    if idx >= len(variants):
        idx = len(variants) - 1
    return _substitute(variants[idx], count=count, replace=replace)


# ── Laravel plural rules ─────────────────────────────────────────────────
# Direct port of Laravel's MessageSelector::getPluralIndex. Each family is a
# small rule keyed by language subtag; the rest of the table is data, so no
# single function carries the whole branch tree.


def _rule_zero(n: int) -> int:
    return 0


def _rule_two_forms(n: int) -> int:
    return 0 if n == 1 else 1


def _rule_zero_or_one(n: int) -> int:
    return 0 if n in (0, 1) else 1


def _rule_slavic(n: int) -> int:
    if n % 10 == 1 and n % 100 != 11:
        return 0
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return 1
    return 2


def _rule_czech(n: int) -> int:
    if n == 1:
        return 0
    return 1 if 2 <= n <= 4 else 2


def _rule_irish(n: int) -> int:
    if n == 1:
        return 0
    return 1 if n == 2 else 2


def _rule_lithuanian(n: int) -> int:
    if n % 10 == 1 and n % 100 != 11:
        return 0
    if n % 10 >= 2 and not (10 <= n % 100 < 20):
        return 1
    return 2


def _rule_slovenian(n: int) -> int:
    if n % 100 == 1:
        return 0
    if n % 100 == 2:
        return 1
    return 2 if n % 100 in (3, 4) else 3


def _rule_macedonian(n: int) -> int:
    return 0 if n % 10 == 1 else 1


def _rule_maltese(n: int) -> int:
    if n == 1:
        return 0
    if n == 0 or 1 < n % 100 < 11:
        return 1
    return 2 if 10 < n % 100 < 20 else 3


def _rule_latvian(n: int) -> int:
    if n == 0:
        return 0
    return 1 if n % 10 == 1 and n % 100 != 11 else 2


def _rule_polish(n: int) -> int:
    if n == 1:
        return 0
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return 1
    return 2


def _rule_welsh(n: int) -> int:
    if n == 1:
        return 0
    if n == 2:
        return 1
    return 2 if n in (8, 11) else 3


def _rule_romanian(n: int) -> int:
    if n == 1:
        return 0
    return 1 if n == 0 or 0 < n % 100 < 20 else 2


def _rule_arabic(n: int) -> int:
    if n == 0:
        return 0
    if n == 1:
        return 1
    if n == 2:
        return 2
    if 3 <= n % 100 <= 10:
        return 3
    return 4 if 11 <= n % 100 <= 99 else 5


_ZERO_LANGS = (
    "az",
    "bo",
    "dz",
    "id",
    "ja",
    "jv",
    "ka",
    "km",
    "kn",
    "ko",
    "ms",
    "th",
    "tr",
    "vi",
    "zh",
)
_TWO_FORM_LANGS = (
    "af",
    "bn",
    "bg",
    "ca",
    "da",
    "de",
    "el",
    "en",
    "eo",
    "es",
    "et",
    "eu",
    "fa",
    "fi",
    "fo",
    "fur",
    "fy",
    "gl",
    "gu",
    "ha",
    "he",
    "hu",
    "is",
    "it",
    "ku",
    "lb",
    "ml",
    "mn",
    "mr",
    "nah",
    "nb",
    "ne",
    "nl",
    "nn",
    "no",
    "om",
    "or",
    "pa",
    "pap",
    "ps",
    "pt",
    "so",
    "sq",
    "sv",
    "sw",
    "ta",
    "te",
    "tk",
    "ur",
    "zu",
)
_ZERO_OR_ONE_LANGS = (
    "am",
    "bh",
    "fil",
    "fr",
    "gun",
    "hi",
    "hy",
    "ln",
    "mg",
    "nso",
    "xbr",
    "ti",
    "wa",
)
_SLAVIC_LANGS = ("be", "bs", "hr", "ru", "sr", "uk")

_PLURAL_RULES: dict[str, Callable[[int], int]] = {
    **dict.fromkeys(_ZERO_LANGS, _rule_zero),
    **dict.fromkeys(_TWO_FORM_LANGS, _rule_two_forms),
    **dict.fromkeys(_ZERO_OR_ONE_LANGS, _rule_zero_or_one),
    **dict.fromkeys(_SLAVIC_LANGS, _rule_slavic),
    "cs": _rule_czech,
    "sk": _rule_czech,
    "ga": _rule_irish,
    "lt": _rule_lithuanian,
    "sl": _rule_slovenian,
    "mk": _rule_macedonian,
    "mt": _rule_maltese,
    "lv": _rule_latvian,
    "pl": _rule_polish,
    "cy": _rule_welsh,
    "ro": _rule_romanian,
    "ar": _rule_arabic,
}


def _plural_index(locale: str, number: int) -> int:
    """Which plural form ``number`` selects for ``locale`` (Laravel parity).

    Matches on the language subtag only (``pt`` from ``pt_BR``), like Laravel.
    Unknown locales fall back to a single form (index 0).
    """
    lang = locale.replace("-", "_").split("_", 1)[0].lower()
    return _PLURAL_RULES.get(lang, _rule_zero)(number)


def _substitute(text: str, *, count: int, replace: Mapping[str, object]) -> str:
    """Replace :placeholder and {placeholder}. Pure str replacement, no eval."""
    result = text
    # Auto-bind :count and {count} from `count` (Laravel convention).
    bindings: dict[str, object] = dict(replace)
    bindings.setdefault("count", count)
    for key, value in bindings.items():
        result = result.replace(f":{key}", str(value))
        result = result.replace("{" + key + "}", str(value))
    return result


__all__ = ["select_plural_variant"]
