"""Laravel-pipe pluralisation + bracket-range syntax."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

_BRACKET_RANGE: Final[re.Pattern[str]] = re.compile(r"^\[(\d+),(\*|\d+)\](.*)$")
_BRACKET_EXACT: Final[re.Pattern[str]] = re.compile(r"^\{(\d+)\}(.*)$")


def select_plural_variant(
    spec: str,
    *,
    count: int,
    replace: Mapping[str, object],
) -> str:
    """Pick the right variant for ``count`` and substitute placeholders.

    Two syntaxes interoperate:
    - Positional pipe: ``"none|one|other"``     count 0|1|>=2 (Laravel-classic).
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

    # Pure positional: index by count if possible, else last.
    if count < len(variants):
        idx = count
    else:
        idx = len(variants) - 1
    return _substitute(variants[idx], count=count, replace=replace)


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
