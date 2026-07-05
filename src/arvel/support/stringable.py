"""arvel.support.stringable — a fluent, chainable string wrapper.

Mirrors the ``Str`` static helpers as instance methods that return a new ``Stringable`` (so calls
chain: ``Str.of(x).trim().squish().title()``); terminal methods return plain values (str/int/bool/
list/Collection). The transforms delegate to ``Str`` — imported lazily to avoid the import cycle
(``arvel.support`` imports this module)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from arvel.support import Collection
    from arvel.support import Str as _StrType


def _str() -> type[_StrType]:
    from arvel.support import Str

    return Str


class Stringable:
    def __init__(self, value: str) -> None:
        self._value = value

    def __str__(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return f"Stringable({self._value!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Stringable):
            return self._value == other._value
        if isinstance(other, str):
            return self._value == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._value)

    def to_str(self) -> str:
        return self._value

    # --- case --------------------------------------------------------------
    def upper(self) -> Stringable:
        return Stringable(self._value.upper())

    def lower(self) -> Stringable:
        return Stringable(self._value.lower())

    def ucfirst(self) -> Stringable:
        return Stringable(_str().ucfirst(self._value))

    def lcfirst(self) -> Stringable:
        return Stringable(_str().lcfirst(self._value))

    def title(self) -> Stringable:
        return Stringable(_str().title(self._value))

    def headline(self) -> Stringable:
        return Stringable(_str().headline(self._value))

    # --- inflection transforms --------------------------------------------
    def snake(self) -> Stringable:
        return Stringable(_str().snake(self._value))

    def camel(self) -> Stringable:
        return Stringable(_str().camel(self._value))

    def studly(self) -> Stringable:
        return Stringable(_str().studly(self._value))

    def kebab(self) -> Stringable:
        return Stringable(_str().kebab(self._value))

    def slug(self, separator: str = "-") -> Stringable:
        return Stringable(_str().slug(self._value, separator))

    def plural(self) -> Stringable:
        return Stringable(_str().plural(self._value))

    def singular(self) -> Stringable:
        return Stringable(_str().singular(self._value))

    # --- concat / affixes --------------------------------------------------
    def append(self, *parts: str) -> Stringable:
        return Stringable(self._value + "".join(parts))

    def prepend(self, *parts: str) -> Stringable:
        return Stringable("".join(parts) + self._value)

    def start(self, prefix: str) -> Stringable:
        return Stringable(_str().start(self._value, prefix))

    def finish(self, cap: str) -> Stringable:
        return Stringable(_str().finish(self._value, cap))

    def chop_start(self, needle: str) -> Stringable:
        return Stringable(_str().chop_start(self._value, needle))

    def chop_end(self, needle: str) -> Stringable:
        return Stringable(_str().chop_end(self._value, needle))

    def wrap(self, before: str, after: str | None = None) -> Stringable:
        return Stringable(_str().wrap(self._value, before, after))

    # --- replace -----------------------------------------------------------
    def replace(self, search: str, replacement: str) -> Stringable:
        return Stringable(self._value.replace(search, replacement))

    def replace_first(self, search: str, replacement: str) -> Stringable:
        return Stringable(_str().replace_first(search, replacement, self._value))

    def replace_last(self, search: str, replacement: str) -> Stringable:
        return Stringable(_str().replace_last(search, replacement, self._value))

    def remove(self, search: str) -> Stringable:
        return Stringable(_str().remove(search, self._value))

    def swap(self, replacements: dict[str, str]) -> Stringable:
        return Stringable(_str().swap(replacements, self._value))

    def mask(self, char: str = "*", index: int = 0, length: int | None = None) -> Stringable:
        return Stringable(_str().mask(self._value, char, index, length))

    # --- slicing / shaping -------------------------------------------------
    def after(self, search: str) -> Stringable:
        return Stringable(self._value.split(search, 1)[1] if search in self._value else self._value)

    def before(self, search: str) -> Stringable:
        return Stringable(self._value.split(search, 1)[0] if search in self._value else self._value)

    def between(self, start: str, end: str) -> Stringable:
        return Stringable(_str().between(self._value, start, end))

    def substr(self, start: int, length: int | None = None) -> Stringable:
        return Stringable(_str().substr(self._value, start, length))

    def take(self, count: int) -> Stringable:
        return Stringable(_str().take(self._value, count))

    def limit(self, length: int = 100, end: str = "...") -> Stringable:
        text = self._value
        return Stringable(text if len(text) <= length else text[:length].rstrip() + end)

    def words(self, words: int = 100, end: str = "...") -> Stringable:
        return Stringable(_str().words(self._value, words, end))

    def reverse(self) -> Stringable:
        return Stringable(self._value[::-1])

    def repeat(self, times: int) -> Stringable:
        return Stringable(self._value * times)

    def squish(self) -> Stringable:
        return Stringable(_str().squish(self._value))

    def trim(self, chars: str | None = None) -> Stringable:
        return Stringable(self._value.strip(chars))

    def ltrim(self, chars: str | None = None) -> Stringable:
        return Stringable(self._value.lstrip(chars))

    def rtrim(self, chars: str | None = None) -> Stringable:
        return Stringable(self._value.rstrip(chars))

    def pad_left(self, length: int, pad: str = " ") -> Stringable:
        return Stringable(_str().pad_left(self._value, length, pad))

    def pad_right(self, length: int, pad: str = " ") -> Stringable:
        return Stringable(_str().pad_right(self._value, length, pad))

    def pad_both(self, length: int, pad: str = " ") -> Stringable:
        return Stringable(_str().pad_both(self._value, length, pad))

    # --- fluent control flow ----------------------------------------------
    def when(self, condition: Any, callback: Any, default: Any = None) -> Stringable:
        if condition:
            result = callback(self)
        elif default is not None:
            result = default(self)
        else:
            return self
        return result if isinstance(result, Stringable) else self

    def unless(self, condition: Any, callback: Any, default: Any = None) -> Stringable:
        return self.when(not condition, callback, default)

    def tap(self, callback: Callable[[Stringable], Any]) -> Stringable:
        callback(self)
        return self

    def pipe(self, callback: Callable[[Stringable], Any]) -> Any:
        return callback(self)

    # --- terminal (return plain values) -----------------------------------
    def contains(self, needle: str) -> bool:
        return needle in self._value

    def contains_all(self, needles: Sequence[str]) -> bool:
        return _str().contains_all(self._value, needles)

    def starts_with(self, prefix: str) -> bool:
        return self._value.startswith(prefix)

    def ends_with(self, suffix: str) -> bool:
        return self._value.endswith(suffix)

    def length(self) -> int:
        return len(self._value)

    def word_count(self) -> int:
        return len(self._value.split())

    def char_at(self, index: int) -> str | None:
        return _str().char_at(self._value, index)

    def position(self, needle: str) -> int | None:
        return _str().position(self._value, needle)

    def is_empty(self) -> bool:
        return self._value == ""

    def is_not_empty(self) -> bool:
        return self._value != ""

    def is_json(self) -> bool:
        return _str().is_json(self._value)

    def is_url(self) -> bool:
        return _str().is_url(self._value)

    def is_uuid(self) -> bool:
        return _str().is_uuid(self._value)

    def is_ulid(self) -> bool:
        return _str().is_ulid(self._value)

    def explode(self, delimiter: str, limit: int = -1) -> Collection[str]:
        """Split into a ``Collection``. ``limit`` is Python
        ``str.split`` maxsplit: the default ``-1`` means no limit (all parts) and positive values cap
        the splits — note this differs from PHP ``explode``'s negative-limit "drop last N" behavior."""
        from arvel.support import Collection

        return Collection(self._value.split(delimiter, limit))
