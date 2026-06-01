"""``Str`` — Laravel-parity string facade."""

from __future__ import annotations

import re
import secrets
import string
import unicodedata
from typing import Final

# ── case-conversion internals ───────────────────────────────────────────────

_SPLIT_BOUNDARY: Final = re.compile(r"[-\s]+")
_INSERT_BEFORE_CAP: Final = re.compile(r"(.)([A-Z][a-z]+)")
_INSERT_BEFORE_LOWER_CAP: Final = re.compile(r"([a-z0-9])([A-Z])")
_COLLAPSE_UNDERSCORES: Final = re.compile(r"_+")

_UUID_RE: Final = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_WORD_RE: Final = re.compile(r"\S+")
_NON_ALNUM_RE: Final = re.compile(r"[^a-z0-9]+")


def _snake(name: str) -> str:
    name = _SPLIT_BOUNDARY.sub("_", name)
    name = _INSERT_BEFORE_CAP.sub(r"\1_\2", name)
    name = _INSERT_BEFORE_LOWER_CAP.sub(r"\1_\2", name)
    name = _COLLAPSE_UNDERSCORES.sub("_", name)
    return name.lower().strip("_")


def _camel(name: str) -> str:
    parts = [p for p in _snake(name).split("_") if p]
    if not parts:
        return ""
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def _pascal(name: str) -> str:
    parts = [p for p in _snake(name).split("_") if p]
    return "".join(p[:1].upper() + p[1:] for p in parts)


def _kebab(name: str) -> str:
    return _snake(name).replace("_", "-")


def _strip_accents(text: str) -> str:
    """Drop combining diacritics: ``café`` → ``cafe``."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


# ── coercion internals ──────────────────────────────────────────────────────

_TRUE_VALUES: Final = frozenset({"true", "1", "yes", "y", "on"})
_FALSE_VALUES: Final = frozenset({"false", "0", "no", "n", "off"})


def _normalize(value: object) -> str:
    if value is None:
        raise ValueError("Value cannot be None")
    result = str(value).strip()
    if not result:
        raise ValueError("Value cannot be empty")
    return result


# ── public class ────────────────────────────────────────────────────────────


class Str:
    """Laravel ``Illuminate\\Support\\Str`` parity helpers, all static."""

    # ── case conversion ─────────────────────────────────────────────────

    @staticmethod
    def snake(text: str) -> str:
        return _snake(text)

    @staticmethod
    def camel(text: str) -> str:
        return _camel(text)

    @staticmethod
    def kebab(text: str) -> str:
        return _kebab(text)

    @staticmethod
    def studly(text: str) -> str:
        """PascalCase; Laravel calls this ``Str::studly``."""
        return _pascal(text)

    @staticmethod
    def pascal(text: str) -> str:
        return _pascal(text)

    @staticmethod
    def plural(value: str) -> str:
        """Naive English pluralization used by the code generators.

        ``post`` → ``posts``, ``category`` → ``categories``. Already-plural
        words (trailing ``s``) are left alone. Irregulars (``person``,
        ``child``) aren't handled — override the table name when it matters.
        """
        if not value:
            return value
        if value.endswith("s"):
            return value
        if value.endswith("y"):
            return value[:-1] + "ies"
        return value + "s"

    # ── slug / headline ─────────────────────────────────────────────────

    @staticmethod
    def slug(text: str, *, separator: str = "-") -> str:
        if not text:
            return ""
        stripped = _strip_accents(text).lower()
        boundary = re.compile(rf"[^a-z0-9{re.escape(separator)}]+")
        stripped = boundary.sub(separator, stripped)
        if separator != "-":
            stripped = stripped.replace("-", separator)
        collapse = re.compile(rf"{re.escape(separator)}+")
        return collapse.sub(separator, stripped).strip(separator)

    @staticmethod
    def headline(text: str) -> str:
        """``hello_world_greeting`` / ``helloWorld`` → ``Hello World …``."""
        return " ".join(word.capitalize() for word in _snake(text).split("_") if word)

    # ── predicates / counts ─────────────────────────────────────────────

    @staticmethod
    def is_uuid(value: str) -> bool:
        return bool(_UUID_RE.match(value))

    @staticmethod
    def word_count(text: str) -> int:
        return len(_WORD_RE.findall(text))

    # ── truncate / pad ──────────────────────────────────────────────────

    @staticmethod
    def limit(text: str, length: int, *, end: str = "...") -> str:
        if len(text) <= length:
            return text
        return text[:length] + end

    @staticmethod
    def pad_left(text: str, length: int, pad_char: str = " ") -> str:
        if len(text) >= length:
            return text
        return text.rjust(length, pad_char)

    @staticmethod
    def pad_right(text: str, length: int, pad_char: str = " ") -> str:
        if len(text) >= length:
            return text
        return text.ljust(length, pad_char)

    @staticmethod
    def pad_both(text: str, length: int, pad_char: str = " ") -> str:
        if len(text) >= length:
            return text
        return text.center(length, pad_char)

    # ── starts/ends/contains ────────────────────────────────────────────

    @staticmethod
    def starts_with(haystack: str, needles: str | tuple[str, ...]) -> bool:
        return haystack.startswith(needles)

    @staticmethod
    def ends_with(haystack: str, needles: str | tuple[str, ...]) -> bool:
        return haystack.endswith(needles)

    @staticmethod
    def contains(haystack: str, needles: str | tuple[str, ...]) -> bool:
        if isinstance(needles, str):
            return needles in haystack
        return any(n in haystack for n in needles)

    # ── after / before / between ────────────────────────────────────────

    @staticmethod
    def after(subject: str, search: str) -> str:
        idx = subject.find(search)
        if idx == -1:
            return subject
        return subject[idx + len(search) :]

    @staticmethod
    def after_last(subject: str, search: str) -> str:
        idx = subject.rfind(search)
        if idx == -1:
            return subject
        return subject[idx + len(search) :]

    @staticmethod
    def before(subject: str, search: str) -> str:
        idx = subject.find(search)
        if idx == -1:
            return subject
        return subject[:idx]

    @staticmethod
    def before_last(subject: str, search: str) -> str:
        idx = subject.rfind(search)
        if idx == -1:
            return subject
        return subject[:idx]

    @staticmethod
    def between(subject: str, before: str, after: str) -> str:
        return Str.before(Str.after(subject, before), after)

    # ── random ──────────────────────────────────────────────────────────

    _ALNUM: Final = string.ascii_letters + string.digits

    @staticmethod
    def random(length: int = 16) -> str:
        if length <= 0:
            msg = "length must be positive"
            raise ValueError(msg)
        return "".join(secrets.choice(Str._ALNUM) for _ in range(length))

    @staticmethod
    def password(
        length: int = 32,
        *,
        letters: bool = True,
        numbers: bool = True,
        symbols: bool = True,
        spaces: bool = False,
    ) -> str:
        """Generate a cryptographically secure random password string.

        Matches Laravel's ``Str::password`` — returns the password *plaintext*,
        not a hash. Pass the result to ``Hash.make()`` to store it.
        """
        if length <= 0:
            msg = "length must be positive"
            raise ValueError(msg)
        pool = ""
        if letters:
            pool += string.ascii_letters
        if numbers:
            pool += string.digits
        if symbols:
            pool += string.punctuation
        if spaces:
            pool += " "
        if not pool:
            msg = "Str.password requires at least one character class"
            raise ValueError(msg)
        return "".join(secrets.choice(pool) for _ in range(length))

    # ── coercion ────────────────────────────────────────────────────────

    @staticmethod
    def to_bool(value: object) -> bool:
        s = _normalize(value).lower()
        if s in _TRUE_VALUES:
            return True
        if s in _FALSE_VALUES:
            return False
        raise ValueError(f"Invalid boolean value: {value!r}")

    @staticmethod
    def to_int(value: object) -> int:
        s = _normalize(value)
        try:
            return int(s)
        except ValueError as exc:
            raise ValueError(f"Invalid integer value: {value!r}") from exc

    @staticmethod
    def to_float(value: object) -> float:
        s = _normalize(value)
        try:
            return float(s)
        except ValueError as exc:
            raise ValueError(f"Invalid float value: {value!r}") from exc

    @staticmethod
    def to_list(
        value: object,
        separator: str = ",",
        *,
        strip_items: bool = True,
        remove_empty: bool = False,
    ) -> list[str]:
        s = _normalize(value)
        items = s.split(separator)
        if strip_items:
            items = [item.strip() for item in items]
        if remove_empty:
            items = [item for item in items if item]
        return items

    @staticmethod
    def to_dict(
        value: object,
        item_separator: str = ",",
        key_value_separator: str = "=",
    ) -> dict[str, str]:
        s = _normalize(value)
        result: dict[str, str] = {}
        for item in s.split(item_separator):
            _item = _normalize(item)
            if not _item:
                continue
            if key_value_separator not in _item:
                raise ValueError(f"Invalid key-value pair: {_item!r}")
            key, val = _item.split(key_value_separator, 1)
            key = _normalize(key)
            val = _normalize(val)
            if not key:
                raise ValueError(f"Empty key in pair: {_item!r}")
            result[key] = val
        return result


__all__ = ["Str"]
