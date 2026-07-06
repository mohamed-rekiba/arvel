"""arvel.support — shared leaf utilities (Collection, Str, helpers).

A dependency-light leaf any module may import. Uses core deps inflection /
python-slugify / python-ulid (all light). parity for Collection + Str.
"""

from __future__ import annotations

import contextvars
import functools
import itertools
import re
from collections.abc import Callable, Iterable, Iterator, Sequence
from typing import Any, cast

import inflection
from slugify import slugify as _slugify
from ulid import ULID

from arvel.support.concurrency import Concurrency
from arvel.support.context import Context
from arvel.support.helpers import (
    Arr,
    blank,
    cache,
    data_get,
    data_set,
    filled,
    optional,
    pipe,
    rescue,
    retry,
    tap,
    throw_if,
    throw_unless,
    value,
)
from arvel.support.money import Currency, Money
from arvel.support.number import Number
from arvel.support.pipeline import Pipeline
from arvel.support.process import (
    InvokedProcess,
    Process,
    ProcessFailed,
    ProcessResult,
    ProcessTimedOut,
)
from arvel.support.stringable import Stringable

#: The authenticated principal for the current request/async context. Lives here (a core leaf
#: both ``auth`` and ``http`` import downward) so neither imports the other (DR-0026); re-exported
#: as ``arvel.auth.current_user`` / ``arvel.http.request.current_user`` for back-compat.
current_user: contextvars.ContextVar[Any] = contextvars.ContextVar("arvel_user", default=None)
#: The active API access token (``ApiToken | None``, typed ``Any`` to avoid a support→database
#: import) — lives here beside ``current_user`` so the http kernel resets it per request (auth is
#: above http and can't be imported by the kernel). ``auth.tokens`` sets/reads it via this handle.
access_token: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "arvel_access_token", default=None
)

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$", re.IGNORECASE)


class Collection[T]:
    """A fluent wrapper over a list."""

    def __init__(self, items: Iterable[T] | None = None) -> None:
        self._items: list[T] = list(items) if items is not None else []

    def all(self) -> list[T]:
        return list(self._items)

    def to_list(self) -> list[T]:
        return list(self._items)

    def __iter__(self) -> Iterator[T]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Collection) and self.all() == other.all()

    def __repr__(self) -> str:
        return f"Collection({self._items!r})"

    def map[R](self, fn: Callable[[T], R]) -> Collection[R]:
        return Collection(fn(x) for x in self._items)

    def filter(self, fn: Callable[[T], bool]) -> Collection[T]:
        return Collection(x for x in self._items if fn(x))

    def each(self, fn: Callable[[T], Any]) -> Collection[T]:
        for x in self._items:
            fn(x)
        return self

    def reduce[R](self, fn: Callable[[R, T], R], initial: R) -> R:
        acc = initial
        for x in self._items:
            acc = fn(acc, x)
        return acc

    def first(self, default: T | None = None) -> T | None:
        return self._items[0] if self._items else default

    def last(self, default: T | None = None) -> T | None:
        return self._items[-1] if self._items else default

    def pluck(self, key: str) -> Collection[Any]:
        return Collection(self._get(x, key) for x in self._items)

    def where(self, key: str, value: Any) -> Collection[T]:
        return Collection(x for x in self._items if self._get(x, key) == value)

    def where_in(self, key: str, values: Iterable[Any]) -> Collection[T]:
        allowed = list(values)
        return Collection(x for x in self._items if self._get(x, key) in allowed)

    def where_not_in(self, key: str, values: Iterable[Any]) -> Collection[T]:
        blocked = list(values)
        return Collection(x for x in self._items if self._get(x, key) not in blocked)

    def where_null(self, key: str) -> Collection[T]:
        return Collection(x for x in self._items if self._get(x, key) is None)

    def where_not_null(self, key: str) -> Collection[T]:
        return Collection(x for x in self._items if self._get(x, key) is not None)

    def take(self, count: int) -> Collection[T]:
        """The first ``count`` items, or the last ``|count|`` when negative."""
        return Collection(self._items[count:] if count < 0 else self._items[:count])

    def contains(self, item: T) -> bool:
        return item in self._items

    def is_empty(self) -> bool:
        return not self._items

    def count(self) -> int:
        return len(self._items)

    def sum(self, key: str | Callable[[T], Any] | None = None) -> Any:
        if key is None:
            return sum(cast("Iterable[Any]", self._items))
        return sum(key(item) if callable(key) else self._get(item, key) for item in self._items)

    def sort(
        self, key: Callable[[T], Any] | None = None, *, reverse: bool = False
    ) -> Collection[T]:
        ordered = sorted(self._items, key=cast("Any", key), reverse=reverse)
        return Collection(ordered)

    def unique(self) -> Collection[T]:
        seen: list[T] = []
        for x in self._items:
            if x not in seen:
                seen.append(x)
        return Collection(seen)

    def chunk(self, size: int) -> Collection[list[T]]:
        if size <= 0:
            return Collection([])
        return Collection([self._items[i : i + size] for i in range(0, len(self._items), size)])

    def flatten(self) -> Collection[Any]:
        return Collection(Arr.flatten(self._items))

    def group_by(self, key: str | Callable[[T], Any]) -> dict[Any, list[T]]:
        groups: dict[Any, list[T]] = {}
        for item in self._items:
            group = key(item) if callable(key) else self._get(item, key)
            groups.setdefault(group, []).append(item)
        return groups

    def key_by(self, key: str | Callable[[T], Any]) -> dict[Any, T]:
        return {
            (key(item) if callable(key) else self._get(item, key)): item for item in self._items
        }

    def sort_by(self, key: str | Callable[[T], Any], *, reverse: bool = False) -> Collection[T]:
        def keyfn(item: T) -> Any:
            return key(item) if callable(key) else self._get(item, key)

        return Collection(sorted(self._items, key=keyfn, reverse=reverse))

    def map_with_keys(self, fn: Callable[[T], tuple[Any, Any]]) -> dict[Any, Any]:
        return dict(fn(item) for item in self._items)

    # --- aggregates --------------------------------------------------------
    def avg(self, key: str | Callable[[T], Any] | None = None) -> Any:
        if not self._items:
            return None
        return self.sum(key) / len(self._items)

    def max(self) -> Any:
        return max(cast("Iterable[Any]", self._items)) if self._items else None

    def min(self) -> Any:
        return min(cast("Iterable[Any]", self._items)) if self._items else None

    def count_by(self, key: str | Callable[[T], Any] | None = None) -> dict[Any, int]:
        counts: dict[Any, int] = {}
        for item in self._items:
            group = item if key is None else (key(item) if callable(key) else self._get(item, key))
            counts[group] = counts.get(group, 0) + 1
        return counts

    def duplicates(self, key: str | Callable[[T], Any] | None = None) -> dict[int, T]:
        """Items that repeat an earlier value (by ``key``, or the item itself), preserving
        first-seen order — ``duplicates``, keyed by **list index** here rather than
        the original array keys."""
        seen: set[Any] = set()
        result: dict[int, T] = {}
        for index, item in enumerate(self._items):
            marker = item if key is None else (key(item) if callable(key) else self._get(item, key))
            if marker in seen:
                result[index] = item
            else:
                seen.add(marker)
        return result

    # --- filtering / selection ---------------------------------------------
    def reject(self, fn: Callable[[T], bool]) -> Collection[T]:
        return Collection(x for x in self._items if not fn(x))

    def every(self, fn: Callable[[T], bool]) -> bool:
        return all(fn(x) for x in self._items)

    def partition(self, fn: Callable[[T], bool]) -> tuple[Collection[T], Collection[T]]:
        yes: list[T] = []
        no: list[T] = []
        for x in self._items:
            (yes if fn(x) else no).append(x)
        return Collection(yes), Collection(no)

    def search(self, value: T | Callable[[T], bool]) -> int | None:
        for i, x in enumerate(self._items):
            if value(x) if callable(value) else x == value:
                return i
        return None

    def value(self, key: str, default: Any = None) -> Any:
        return self._get(self._items[0], key) if self._items else default

    # --- ordering / slicing ------------------------------------------------
    def reverse(self) -> Collection[T]:
        return Collection(reversed(self._items))

    def sort_desc(self) -> Collection[T]:
        return self.sort(reverse=True)

    def sort_by_desc(self, key: str | Callable[[T], Any]) -> Collection[T]:
        return self.sort_by(key, reverse=True)

    def skip(self, count: int) -> Collection[T]:
        return Collection(self._items[count:])

    def slice(self, offset: int, length: int | None = None) -> Collection[T]:
        if length is None:
            end: int | None = None
        elif length < 0:
            end = length  # negative length = stop that many from the end
        else:
            end = offset + length
        return Collection(self._items[offset:end])

    def nth(self, step: int, offset: int = 0) -> Collection[T]:
        return Collection(self._items[offset::step])

    # --- combining ---------------------------------------------------------
    def merge(self, other: Iterable[T]) -> Collection[T]:
        return Collection([*self._items, *other])

    def concat(self, other: Iterable[T]) -> Collection[T]:
        return Collection([*self._items, *other])

    def flat_map[R](self, fn: Callable[[T], Iterable[R]]) -> Collection[R]:
        return Collection(y for x in self._items for y in fn(x))

    def zip(self, *iterables: Iterable[Any]) -> Collection[Collection[Any]]:
        """Pair this collection's items index-wise with each iterable — ``zip``. Stops at
        the shortest input, like the builtin ``zip``."""
        return Collection(Collection(row) for row in zip(self._items, *iterables, strict=False))

    def combine(self, values: Iterable[Any]) -> dict[Any, Any]:
        """This collection's items as keys, paired with ``values`` — ``combine``. The two
        must be the same length (a mismatch raises), same as the underlying ``array_combine``."""
        return dict(zip(self._items, values, strict=True))

    def implode(self, glue: str, key: str | None = None) -> str:
        parts = self._items if key is None else [self._get(x, key) for x in self._items]
        return glue.join(str(p) for p in parts)

    def join(self, glue: str, key: str | None = None) -> str:
        """alias for ``implode``."""
        return self.implode(glue, key)

    # --- fluent control flow -----------------------------------------------
    def tap(self, fn: Callable[[Collection[T]], Any]) -> Collection[T]:
        fn(self)
        return self

    def pipe[R](self, fn: Callable[[Collection[T]], R]) -> R:
        return fn(self)

    def when(self, condition: Any, callback: Any, default: Any = None) -> Collection[T]:
        if condition:
            result = callback(self)
        elif default is not None:
            result = default(self)
        else:
            return self
        return cast("Collection[T]", result) if isinstance(result, Collection) else self

    def unless(self, condition: Any, callback: Any, default: Any = None) -> Collection[T]:
        return self.when(not condition, callback, default)

    def when_empty(self, callback: Any, default: Any = None) -> Collection[T]:
        """Run ``callback`` only when this collection is empty — ``whenEmpty``."""
        return self.when(self.is_empty(), callback, default)

    def when_not_empty(self, callback: Any, default: Any = None) -> Collection[T]:
        """Run ``callback`` only when this collection is NOT empty — ``whenNotEmpty``."""
        return self.when(not self.is_empty(), callback, default)

    def lazy(self) -> LazyCollection[T]:
        """A deferred, re-iterable view over this collection's items."""
        return LazyCollection(lambda: iter(self._items))

    @staticmethod
    def _get(item: Any, key: str) -> Any:
        if isinstance(item, dict):
            return cast("dict[str, Any]", item).get(key)
        return getattr(item, key, None)


class LazyCollection[T]:
    """A generator-backed Collection: ``map``/``filter``/
    ``take`` are deferred and stream one element at a time. Built from an iterable or a
    zero-arg callable returning a fresh iterator (the latter keeps it re-iterable)."""

    def __init__(self, source: Iterable[T] | Callable[[], Iterator[T]]) -> None:
        if callable(source) and not hasattr(source, "__iter__"):
            self._make: Callable[[], Iterator[T]] = source
        else:
            iterable = cast("Iterable[T]", source)
            self._make = lambda: iter(iterable)

    def __iter__(self) -> Iterator[T]:
        return self._make()

    def map[R](self, fn: Callable[[T], R]) -> LazyCollection[R]:
        return LazyCollection(lambda: (fn(x) for x in self))

    def filter(self, fn: Callable[[T], bool]) -> LazyCollection[T]:
        return LazyCollection(lambda: (x for x in self if fn(x)))

    def each(self, fn: Callable[[T], Any]) -> LazyCollection[T]:
        for x in self:
            fn(x)
        return self

    def take(self, count: int) -> LazyCollection[T]:
        return LazyCollection(lambda: itertools.islice(self, count))

    def first(self, default: T | None = None) -> T | None:
        for x in self:
            return x
        return default

    def to_list(self) -> list[T]:
        return list(self)

    def all(self) -> list[T]:
        return list(self)

    def collect(self) -> Collection[T]:
        """Materialize into an eager ``Collection``."""
        return Collection(self.to_list())


class Str:
    """String helpers over inflection / slugify / ulid."""

    # Memoized: these regex-heavy transforms are called hot (table-name / relation-key derivation).
    # ``ulid()`` and the predicates below are intentionally NOT cached.
    @staticmethod
    @functools.lru_cache(maxsize=2048)
    def studly(value: str) -> str:
        return inflection.camelize(value)

    @staticmethod
    @functools.lru_cache(maxsize=2048)
    def camel(value: str) -> str:
        return inflection.camelize(value, False)

    @staticmethod
    @functools.lru_cache(maxsize=2048)
    def snake(value: str) -> str:
        return inflection.underscore(value)

    @staticmethod
    @functools.lru_cache(maxsize=2048)
    def kebab(value: str) -> str:
        return inflection.dasherize(inflection.underscore(value))

    @staticmethod
    @functools.lru_cache(maxsize=2048)
    def slug(value: str, separator: str = "-") -> str:
        return _slugify(value, separator=separator)

    @staticmethod
    @functools.lru_cache(maxsize=2048)
    def plural(value: str) -> str:
        return inflection.pluralize(value)

    @staticmethod
    @functools.lru_cache(maxsize=2048)
    def singular(value: str) -> str:
        return inflection.singularize(value)

    @staticmethod
    @functools.lru_cache(maxsize=2048)
    def title(value: str) -> str:
        return inflection.titleize(value)

    @staticmethod
    def ulid() -> str:
        return str(ULID())

    @staticmethod
    def contains(haystack: str, needle: str) -> bool:
        return needle in haystack

    @staticmethod
    def starts_with(value: str, prefix: str) -> bool:
        return value.startswith(prefix)

    @staticmethod
    def ends_with(value: str, suffix: str) -> bool:
        return value.endswith(suffix)

    @staticmethod
    def limit(value: str, length: int = 100, end: str = "...") -> str:
        return value if len(value) <= length else value[:length].rstrip() + end

    @staticmethod
    def after(value: str, search: str) -> str:
        return value.split(search, 1)[1] if search in value else value

    @staticmethod
    def before(value: str, search: str) -> str:
        return value.split(search, 1)[0] if search in value else value

    @staticmethod
    def after_last(value: str, search: str) -> str:
        """Everything after the LAST occurrence of ``search`` (the whole string if absent/empty)."""
        return value.rpartition(search)[2] if search and search in value else value

    @staticmethod
    def before_last(value: str, search: str) -> str:
        """Everything before the LAST occurrence of ``search`` (the whole string if absent/empty)."""
        return value.rpartition(search)[0] if search and search in value else value

    @staticmethod
    def is_(pattern: str, value: str) -> bool:
        """Whether ``value`` matches ``pattern``. Only ``*`` is a wildcard
        (matches any run of characters, including ``/``); every other character is literal."""
        if pattern == value:
            return True
        regex = re.escape(pattern).replace(r"\*", ".*")
        return re.fullmatch(regex, value) is not None

    @staticmethod
    @functools.lru_cache(maxsize=2048)
    def headline(value: str) -> str:
        return inflection.titleize(inflection.underscore(value))

    @staticmethod
    def is_uuid(value: str) -> bool:
        return bool(_UUID_RE.match(value))

    @staticmethod
    def mask(value: str, char: str = "*", index: int = 0, length: int | None = None) -> str:
        end = len(value) if length is None else index + length
        return value[:index] + char * (min(end, len(value)) - index) + value[end:]

    @staticmethod
    def of(value: str) -> Stringable:
        return Stringable(value)

    @staticmethod
    def random(length: int = 16) -> str:
        """A cryptographically-random alphanumeric string."""
        import secrets
        import string

        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    # --- case --------------------------------------------------------------
    @staticmethod
    def lower(value: str) -> str:
        return value.lower()

    @staticmethod
    def upper(value: str) -> str:
        return value.upper()

    @staticmethod
    def ucfirst(value: str) -> str:
        return value[:1].upper() + value[1:]

    @staticmethod
    def lcfirst(value: str) -> str:
        return value[:1].lower() + value[1:]

    # --- length / slicing --------------------------------------------------
    @staticmethod
    def length(value: str) -> int:
        return len(value)

    @staticmethod
    def substr(value: str, start: int, length: int | None = None) -> str:
        return value[start:] if length is None else value[start : start + length]

    @staticmethod
    def take(value: str, count: int) -> str:
        """First ``count`` chars, or the last ``-count`` when negative."""
        return value[:count] if count >= 0 else value[count:]

    @staticmethod
    def char_at(value: str, index: int) -> str | None:
        try:
            return value[index]
        except IndexError:
            return None

    @staticmethod
    def reverse(value: str) -> str:
        return value[::-1]

    @staticmethod
    def repeat(value: str, times: int) -> str:
        return value * times

    @staticmethod
    def word_count(value: str) -> int:
        return len(value.split())

    @staticmethod
    def words(value: str, words: int = 100, end: str = "...") -> str:
        parts = value.split()
        return value if len(parts) <= words else " ".join(parts[:words]) + end

    # --- trimming / padding / whitespace -----------------------------------
    @staticmethod
    def squish(value: str) -> str:
        """Collapse all runs of whitespace to single spaces and trim."""
        return " ".join(value.split())

    @staticmethod
    def pad_left(value: str, length: int, pad: str = " ") -> str:
        return value.rjust(length, pad)

    @staticmethod
    def pad_right(value: str, length: int, pad: str = " ") -> str:
        return value.ljust(length, pad)

    @staticmethod
    def pad_both(value: str, length: int, pad: str = " ") -> str:
        return value.center(length, pad)

    # --- prefix / suffix ---------------------------------------------------
    @staticmethod
    def start(value: str, prefix: str) -> str:
        """Ensure ``value`` begins with a single ``prefix``."""
        return value if value.startswith(prefix) else prefix + value

    @staticmethod
    def finish(value: str, cap: str) -> str:
        """Ensure ``value`` ends with a single ``cap``."""
        return value if value.endswith(cap) else value + cap

    @staticmethod
    def chop_start(value: str, needle: str) -> str:
        return value.removeprefix(needle)

    @staticmethod
    def chop_end(value: str, needle: str) -> str:
        return value.removesuffix(needle)

    @staticmethod
    def wrap(value: str, before: str, after: str | None = None) -> str:
        return f"{before}{value}{after if after is not None else before}"

    # --- search / extract --------------------------------------------------
    @staticmethod
    def between(value: str, start: str, end: str) -> str:
        """The substring between the first ``start`` and the **last** ``end``
        ``beforeLast(after($subject, $from), $to)``."""
        if start == "" or end == "":
            return value
        after_start = Str.after(value, start)
        head, sep, _ = after_start.rpartition(end)
        return head if sep else after_start

    @staticmethod
    def contains_all(haystack: str, needles: Sequence[str]) -> bool:
        return all(n in haystack for n in needles)

    @staticmethod
    def position(haystack: str, needle: str) -> int | None:
        index = haystack.find(needle)
        return None if index < 0 else index

    # --- replace -----------------------------------------------------------
    @staticmethod
    def replace_first(search: str, replace: str, subject: str) -> str:
        return subject.replace(search, replace, 1) if search else subject

    @staticmethod
    def replace_last(search: str, replace: str, subject: str) -> str:
        if not search or search not in subject:
            return subject
        head, _, tail = subject.rpartition(search)
        return head + replace + tail

    @staticmethod
    def replace_array(search: str, replacements: Sequence[str], subject: str) -> str:
        """Replace successive occurrences of ``search`` with each value in turn (
        ``Str::replaceArray``)."""
        result = subject
        for replacement in replacements:
            if search not in result:
                break
            result = result.replace(search, replacement, 1)
        return result

    @staticmethod
    def remove(search: str, subject: str) -> str:
        return subject.replace(search, "")

    @staticmethod
    def swap(replacements: dict[str, str], subject: str) -> str:
        """Replace each key with its value in a SINGLE pass:
        substituted text is never re-processed, so ``{'a':'b','b':'a'}`` on ``'ab'`` → ``'ba'``.
        Longer keys win on overlap."""
        if not replacements:
            return subject
        keys = sorted(replacements, key=len, reverse=True)
        pattern = re.compile("|".join(re.escape(k) for k in keys))
        return pattern.sub(lambda m: replacements[m.group(0)], subject)

    # --- predicates / generators ------------------------------------------
    @staticmethod
    def is_ulid(value: str) -> bool:
        return bool(_ULID_RE.match(value))

    @staticmethod
    def is_json(value: str) -> bool:
        import json

        try:
            json.loads(value)
        except ValueError:  # JSONDecodeError ⊂ ValueError; value is a str so TypeError can't occur
            return False
        return True

    @staticmethod
    def is_url(value: str) -> bool:
        """A lightweight scheme check (http/https/ftp) — intentionally simpler than the full
        URL validator; use a Validator ``url`` rule when strict validation matters."""
        return value.startswith(("http://", "https://", "ftp://"))

    @staticmethod
    def uuid() -> str:
        """A random (v4) UUID string."""
        import uuid as _uuid

        return str(_uuid.uuid4())


__all__ = [
    "Arr",
    "Collection",
    "Concurrency",
    "Context",
    "Currency",
    "InvokedProcess",
    "LazyCollection",
    "Money",
    "Number",
    "Pipeline",
    "Process",
    "ProcessFailed",
    "ProcessResult",
    "ProcessTimedOut",
    "Str",
    "Stringable",
    "blank",
    "cache",
    "current_user",
    "data_get",
    "data_set",
    "filled",
    "optional",
    "pipe",
    "rescue",
    "retry",
    "tap",
    "throw_if",
    "throw_unless",
    "value",
]
