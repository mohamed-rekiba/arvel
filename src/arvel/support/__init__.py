"""arvel.support — shared leaf utilities (Collection, Str, helpers).

A dependency-light leaf any module may import. Uses core deps inflection /
python-slugify / python-ulid (all light). parity for Collection + Str.
"""

from __future__ import annotations

import contextvars
import functools
import itertools
import operator
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
    DumpDie,
    Sleep,
    app_path,
    base_path,
    bcrypt,
    blank,
    cache,
    class_basename,
    collect,
    config_path,
    data_get,
    data_set,
    database_path,
    dd,
    decrypt,
    dump,
    encrypt,
    enum_value,
    event,
    filled,
    info,
    lang_path,
    literal,
    logger,
    noop,
    once,
    optional,
    pipe,
    policy,
    public_path,
    report,
    report_if,
    report_unless,
    rescue,
    resolve,
    resource_path,
    retry,
    storage_path,
    tap,
    throw_if,
    throw_unless,
    transform,
    validator,
    value,
    windows_os,
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
#: Request-scoped view shares (``dict[str, Any] | None`` — e.g. the flashed ``errors``/``old`` a
#: middleware exposes to this request's templates). Lives here beside ``current_user`` for the same
#: DR-0026 reason: ``views`` reads it, ``http`` writes and resets it, and neither may import the
#: other. Per-request data must never go into the Jinja ``env.globals`` — that is process-shared
#: and leaks one request's flash into a concurrent request's render.
view_shares: contextvars.ContextVar[Any] = contextvars.ContextVar("arvel_view_shares", default=None)

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$", re.IGNORECASE)
#: sentinel distinguishing "not passed" from ``None`` in ``Collection.first_where``'s
#: 1/2/3-arg overloads.
_UNSET: Any = object()

_FIRST_WHERE_OPS: dict[str, Callable[[Any, Any], bool]] = {
    "=": operator.eq,
    "==": operator.eq,
    "===": operator.eq,
    "!=": operator.ne,
    "<>": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}


def _first_where_matches(cmp: Callable[[Any, Any], bool], actual: Any, expected: Any) -> bool:
    """``cmp(actual, expected)``, tolerating incomparable types (e.g. ``None`` vs an
    ``int``) as a non-match instead of raising — loose-comparison parity."""
    try:
        return cmp(actual, expected)
    except TypeError:
        return False


class ItemNotFoundException(RuntimeError):
    """``Collection.sole()`` matched nothing — parity with the reference's
    ``ItemNotFoundException``."""


class MultipleItemsFoundException(RuntimeError):
    """``Collection.sole()`` matched more than one item — parity with the reference's
    ``MultipleItemsFoundException``."""


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

    def diff(self, other: Iterable[T]) -> Collection[T]:
        """Items in this collection not present in ``other`` — ``diff``."""
        excluded = list(other)
        return Collection(x for x in self._items if x not in excluded)

    def intersect(self, other: Iterable[T]) -> Collection[T]:
        """Items in this collection also present in ``other`` — ``intersect``."""
        allowed = list(other)
        return Collection(x for x in self._items if x in allowed)

    def contains(self, item: T | Callable[[T], bool]) -> bool:
        if callable(item):
            return any(item(x) for x in self._items)
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

    def _values_for(self, key: str | Callable[[T], Any] | None) -> list[Any]:
        if key is None:
            return list(self._items)
        return [key(item) if callable(key) else self._get(item, key) for item in self._items]

    def median(self, key: str | Callable[[T], Any] | None = None) -> Any:
        values = sorted(self._values_for(key))
        if not values:
            return None
        mid = len(values) // 2
        if len(values) % 2:
            return values[mid]
        return (values[mid - 1] + values[mid]) / 2

    def mode(self, key: str | Callable[[T], Any] | None = None) -> list[Any]:
        """The most frequent value(s) (by ``key``, or the item itself) — ``mode``. Ties
        are all returned, in first-seen order."""
        counts: dict[Any, int] = {}
        order: list[Any] = []
        for marker in self._values_for(key):
            if marker not in counts:
                order.append(marker)
            counts[marker] = counts.get(marker, 0) + 1
        if not counts:
            return []
        peak = max(counts.values())
        return [marker for marker in order if counts[marker] == peak]

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

    def first_where(self, key: str, op: Any = _UNSET, value: Any = _UNSET) -> T | None:
        """The first item matching a key/value pair — ``firstWhere``. One arg tests
        ``key``'s value for truthiness; two args test equality; three args apply a
        comparison operator (``=``/``!=``/``>``/``>=``/``<``/``<=``) between them."""
        if op is _UNSET:
            return next((x for x in self._items if self._get(x, key)), None)
        if value is _UNSET:
            return next((x for x in self._items if self._get(x, key) == op), None)
        cmp = _FIRST_WHERE_OPS.get(op)
        if cmp is None:
            raise ValueError(f"first_where(): unknown operator {op!r}")
        return next(
            (x for x in self._items if _first_where_matches(cmp, self._get(x, key), value)), None
        )

    def sole(self, predicate: Callable[[T], bool] | None = None) -> T:
        """The single item matching ``predicate`` (or the collection's single item when
        omitted) — ``sole``. Raises unless exactly one item qualifies."""
        matches = self._items if predicate is None else [x for x in self._items if predicate(x)]
        if not matches:
            raise ItemNotFoundException("sole(): no item matched")
        if len(matches) > 1:
            raise MultipleItemsFoundException(f"sole(): {len(matches)} items matched")
        return matches[0]

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

    def random(self, n: int | None = None) -> T | Collection[T]:
        """A single random item (``n`` omitted), or a ``Collection`` of ``n`` distinct
        random items — ``random``. Uses ``secrets`` for selection."""
        import secrets

        if n is None:
            if not self._items:
                raise ValueError("random(): the collection is empty")
            return secrets.choice(self._items)
        if n > len(self._items):
            raise ValueError(f"requested {n} items but only {len(self._items)} available")
        pool = list(self._items)
        return Collection(pool.pop(secrets.randbelow(len(pool))) for _ in range(n))

    def shuffle(self) -> Collection[T]:
        """A new collection with items in random order — ``shuffle`` (Fisher-Yates,
        ``secrets``-backed)."""
        import secrets

        shuffled = list(self._items)
        for i in range(len(shuffled) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
        return Collection(shuffled)

    def pad(self, size: int, value: T) -> Collection[T]:
        """Pad to ``|size|`` items with ``value`` — ``pad``. A negative ``size`` pads on
        the left; no-op if the collection already meets the target length."""
        missing = abs(size) - len(self._items)
        if missing <= 0:
            return Collection(self._items)
        padding = [value] * missing
        return Collection([*self._items, *padding] if size >= 0 else [*padding, *self._items])

    def splice(
        self, offset: int, length: int | None = None, replacement: Iterable[T] | None = None
    ) -> Collection[T]:
        """Remove and return the ``[offset:offset+length]`` slice (negative ``length``
        stops that many from the end, matching ``slice``'s convention), optionally
        splicing ``replacement`` in its place — ``splice``. Unlike this class's other
        (non-mutating) methods, splice mutates ``self`` in place — that's the operation's
        whole point in the reference too."""
        end = len(self._items) if length is None else (offset + length if length >= 0 else length)
        removed = self._items[offset:end]
        self._items[offset:end] = list(replacement) if replacement is not None else []
        return Collection(removed)

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

    @staticmethod
    def uuid7() -> str:
        """A time-ordered (v7) UUID string — sorts chronologically, index-friendly."""
        import uuid as _uuid

        return str(_uuid.uuid7())

    # --- regex ---------------------------------------------------------------
    @staticmethod
    def match(pattern: str, subject: str) -> str:
        """The first capturing group of the first match, else the whole match, else
        ``''`` — ``Str::match``."""
        found = re.search(pattern, subject)
        if found is None:
            return ""
        return found.group(1) if found.lastindex else found.group(0)

    @staticmethod
    def match_all(pattern: str, subject: str) -> Collection[str]:
        """Every match (or, with one capturing group, every first-group capture) —
        ``Str::matchAll``. Empty ``Collection`` when nothing matches."""
        found = re.findall(pattern, subject)
        return Collection(cast("str", m[0] if isinstance(m, tuple) else m) for m in found)

    @staticmethod
    def is_match(pattern: str, subject: str) -> bool:
        return re.search(pattern, subject) is not None

    @staticmethod
    def replace_matches(pattern: str, replace: str | Callable[[str], str], subject: str) -> str:
        """Replace every match of ``pattern`` — a plain string, or a callable receiving
        each matched substring and returning its replacement — ``Str::replaceMatches``."""
        if callable(replace):
            return re.sub(pattern, lambda m: replace(m.group(0)), subject)
        return re.sub(pattern, replace, subject)

    # --- transliteration / excerpting ------------------------------------------
    @staticmethod
    def ascii_(value: str) -> str:
        """Transliterate to the closest ASCII representation — ``Str::ascii``. Reuses
        python-slugify's own transliteration engine (an already-installed dependency,
        resolved dynamically the same way slugify itself does, so no stub-less static
        import is needed)."""
        import importlib
        import unicodedata

        try:
            engine: Any = importlib.import_module("unidecode")
        except ImportError:
            engine = importlib.import_module("text_unidecode")
        return cast("str", engine.unidecode(unicodedata.normalize("NFKD", value)))

    @staticmethod
    def excerpt(text: str, phrase: str, radius: int = 100, omission: str = "...") -> str:
        """``radius`` characters either side of the first ``phrase`` match, bracketed by
        ``omission`` where the excerpt was truncated — ``Str::excerpt``. ``''`` if
        ``phrase`` isn't found."""
        if not phrase:
            return text
        index = text.find(phrase)
        if index < 0:
            return ""
        start = max(0, index - radius)
        end = min(len(text), index + len(phrase) + radius)
        result = text[start:end]
        if start > 0:
            result = omission + result
        if end < len(text):
            result = result + omission
        return result

    @staticmethod
    def word_wrap(text: str, characters: int = 76, break_str: str = "\n") -> str:
        """Break ``text`` into lines of at most ``characters`` (splitting only at spaces;
        an overlong single word is never cut) joined by ``break_str`` — ``Str::wordWrap``."""
        lines: list[str] = []
        current = ""
        for word in text.split(" "):
            candidate = word if not current else f"{current} {word}"
            if not current or len(candidate) <= characters:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return break_str.join(lines)

    # --- generators ------------------------------------------------------------
    @staticmethod
    def password(
        length: int = 32,
        *,
        letters: bool = True,
        numbers: bool = True,
        symbols: bool = True,
        spaces: bool = False,
    ) -> str:
        """A cryptographically-random password containing at least one character from
        every enabled class (matching the reference's guarantee), the rest drawn from
        the combined pool — ``Str::password``."""
        import secrets

        classes: list[str] = []
        if letters:
            classes.append("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
        if numbers:
            classes.append("0123456789")
        if symbols:
            classes.append("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")
        if spaces:
            classes.append(" ")
        if not classes:
            raise ValueError("password() needs at least one character class enabled")
        pool = "".join(classes)
        # one guaranteed char per class (when length allows), remainder from the pool
        chars = [secrets.choice(cls) for cls in classes[: max(length, 0)]]
        chars += [secrets.choice(pool) for _ in range(max(length - len(chars), 0))]
        shuffled: list[str] = []
        while chars:
            shuffled.append(chars.pop(secrets.randbelow(len(chars))))
        return "".join(shuffled)

    # --- substr / dedup / base64 ------------------------------------------------
    @staticmethod
    def substr_count(haystack: str, needle: str) -> int:
        return haystack.count(needle)

    @staticmethod
    def substr_replace(subject: str, replace: str, start: int, length: int | None = None) -> str:
        """Replace the ``[start:start+length]`` slice with ``replace`` — ``Str::substrReplace``.
        ``length=0`` inserts without removing; a negative ``start``/``length`` counts from
        the end, mirroring PHP's ``substr_replace``."""
        size = len(subject)
        start = max(size + start, 0) if start < 0 else min(start, size)
        if length is None:
            end = size
        elif length < 0:
            end = max(size + length, start)
        else:
            end = min(start + length, size)
        return subject[:start] + replace + subject[end:]

    @staticmethod
    def deduplicate(value: str, character: str = " ") -> str:
        """Collapse consecutive runs of ``character`` to a single instance — ``Str::deduplicate``."""
        return re.sub(f"{re.escape(character)}+", character, value)

    @staticmethod
    def to_base64(value: str) -> str:
        import base64

        return base64.b64encode(value.encode()).decode()

    @staticmethod
    def from_base64(value: str) -> str:
        import base64

        return base64.b64decode(value).decode()


__all__ = [
    "Arr",
    "Collection",
    "Concurrency",
    "Context",
    "Currency",
    "DumpDie",
    "InvokedProcess",
    "ItemNotFoundException",
    "LazyCollection",
    "Money",
    "MultipleItemsFoundException",
    "Number",
    "Pipeline",
    "Process",
    "ProcessFailed",
    "ProcessResult",
    "ProcessTimedOut",
    "Sleep",
    "Str",
    "Stringable",
    "app_path",
    "base_path",
    "bcrypt",
    "blank",
    "cache",
    "class_basename",
    "collect",
    "config_path",
    "current_user",
    "data_get",
    "data_set",
    "database_path",
    "dd",
    "decrypt",
    "dump",
    "encrypt",
    "enum_value",
    "event",
    "filled",
    "info",
    "lang_path",
    "literal",
    "logger",
    "noop",
    "once",
    "optional",
    "pipe",
    "policy",
    "public_path",
    "report",
    "report_if",
    "report_unless",
    "rescue",
    "resolve",
    "resource_path",
    "retry",
    "storage_path",
    "tap",
    "throw_if",
    "throw_unless",
    "transform",
    "validator",
    "value",
    "windows_os",
]
