"""arvel.support.helpers — Arr, data_get/data_set, and flow helpers.

Dynamic by nature (arbitrary nested data + callables); mypy-strict still checks it.
Grounded in knowledge/port/06-facades.md §helpers.
"""

from __future__ import annotations

import functools
import inspect
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable, Sequence, Sized
    from contextlib import AbstractContextManager

_MISSING: Any = object()


def value(val: Any) -> Any:
    """Resolve a value or a zero-arg callable producing it."""
    return val() if callable(val) else val


def _segment(target: Any, key: str, default: Any) -> Any:
    if isinstance(target, dict):
        return cast("dict[str, Any]", target).get(key, default)
    if isinstance(target, (list, tuple)):
        try:
            return cast("Sequence[Any]", target)[int(key)]
        except ValueError, IndexError:
            return default
    return getattr(target, key, default)


def data_get(target: Any, key: str | Sequence[str] | None, default: Any = None) -> Any:
    """Read a nested value by dot-path, with ``*`` wildcard over lists."""
    if key is None:
        return target
    segments = key.split(".") if isinstance(key, str) else list(key)
    for index, seg in enumerate(segments):
        if seg == "*":
            rest = segments[index + 1 :]
            if not isinstance(target, (list, tuple)):
                return value(default)
            return [
                data_get(item, rest, default) if rest else item
                for item in cast("Sequence[Any]", target)
            ]
        target = _segment(target, seg, _MISSING)
        if target is _MISSING:
            return value(default)
    return target


def data_set(target: Any, key: str, item: Any, *, overwrite: bool = True) -> Any:
    """Set a nested value by dot-path into nested dicts (creating intermediates)."""
    segments = key.split(".")
    node: Any = target
    for seg in segments[:-1]:
        raw: Any = cast("dict[str, Any]", node).get(seg) if isinstance(node, dict) else None
        if isinstance(raw, dict):
            node = cast("dict[str, Any]", raw)
        else:
            created: dict[str, Any] = {}
            node[seg] = created
            node = created
    if overwrite or segments[-1] not in node:
        node[segments[-1]] = item
    return target


def tap(obj: Any, callback: Callable[[Any], Any] | None = None) -> Any:
    """Run ``callback(obj)`` for side effects and return ``obj``."""
    if callback is not None:
        callback(obj)
    return obj


def pipe(obj: Any, *callbacks: Callable[[Any], Any]) -> Any:
    for callback in callbacks:
        obj = callback(obj)
    return obj


def blank(obj: Any) -> bool:
    if obj is None:
        return True
    if isinstance(obj, str):
        return obj.strip() == ""
    if isinstance(obj, (list, tuple, dict, set)):
        return len(cast("Sized", obj)) == 0
    return False


def filled(obj: Any) -> bool:
    return not blank(obj)


def throw_if(condition: Any, exc: type[BaseException] | BaseException) -> Any:
    if condition:
        raise exc() if isinstance(exc, type) else exc
    return condition


def throw_unless(condition: Any, exc: type[BaseException] | BaseException) -> Any:
    """Inverse of ``throw_if`` — raise when ``condition`` is falsy; else return it."""
    if not condition:
        raise exc() if isinstance(exc, type) else exc
    return condition


class _Optional:
    """Null-safe proxy: attribute/item access on a wrapped
    ``None`` yields ``None`` instead of raising; otherwise proxies to the value."""

    __slots__ = ("_value",)

    def __init__(self, value: Any) -> None:
        object.__setattr__(self, "_value", value)

    def __getattr__(self, name: str) -> Any:
        value = object.__getattribute__(self, "_value")
        return None if value is None else getattr(value, name, None)

    def __getitem__(self, key: Any) -> Any:
        value = object.__getattribute__(self, "_value")
        if value is None:
            return None
        try:
            return value[key]
        except KeyError, IndexError, TypeError:
            return None

    def __bool__(self) -> bool:
        return object.__getattribute__(self, "_value") is not None


def optional(value: Any) -> Any:
    """Wrap ``value`` so first-level attribute/item access is null-safe."""
    return _Optional(value)


class Sleep:
    """The sleep seam flow helpers go through — fakeable so retry/backoff tests run instantly.

    ``Sleep.fake()`` captures requested durations instead of sleeping; production code calls
    ``Sleep.sleep``/``Sleep.asleep`` and never blocks under a fake.
    """

    _fake: list[float] | None = None

    @classmethod
    def sleep(cls, seconds: float) -> None:
        if cls._fake is not None:
            cls._fake.append(seconds)
            return
        time.sleep(seconds)

    @classmethod
    async def asleep(cls, seconds: float) -> None:
        if cls._fake is not None:
            cls._fake.append(seconds)
            return
        import asyncio

        await asyncio.sleep(seconds)

    @classmethod
    def fake(cls) -> AbstractContextManager[list[float]]:
        @contextmanager
        def _cm() -> Generator[list[float]]:
            prev: list[float] | None = cls._fake
            recorded: list[float] = []
            cls._fake = recorded
            try:
                yield recorded
            finally:
                cls._fake = prev

        return _cm()


def once(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Memoize ``fn``'s first result per argument tuple (per instance for methods) — the
    stdlib cache with the flow-helper name. On methods the cache strong-refs ``self``, so
    decorated instances live as long as the process — use on services, not per-request objects."""
    return functools.cache(fn)


def _report_to_handler(exc: BaseException) -> None:
    """Best-effort report to the app's bound ExceptionHandler; never raises, no-op without one."""
    from arvel.kernel.globals import has_application

    if not has_application():
        return
    from arvel.contracts import ExceptionHandler
    from arvel.kernel.globals import app as _app

    try:
        handler = _app(ExceptionHandler)
        if handler.should_report(exc):
            handler.report(exc)
    except Exception:
        # a broken handler must not turn a rescued error into a thrown one
        return


def rescue(callback: Callable[[], Any], default: Any = None, *, report: bool = True) -> Any:
    """Run ``callback`` swallowing exceptions into ``default`` — reporting the swallowed
    exception to the bound ExceptionHandler unless ``report=False``. An async *function*
    (incl. a partial of one) returns an awaitable with the same semantics; an object whose
    ``__call__`` is async is not detected — pass the function itself."""
    if inspect.iscoroutinefunction(callback):

        async def _arescue() -> Any:
            try:
                return await callback()
            except Exception as exc:
                if report:
                    _report_to_handler(exc)
                return value(default)

        return _arescue()
    try:
        return callback()
    except Exception as exc:
        if report:
            _report_to_handler(exc)
        return value(default)


def _retry_delay(
    attempt: int, sleep: float, backoff: Sequence[float] | Callable[[int], float] | None
) -> float:
    if backoff is None:
        return sleep
    if callable(backoff):
        return backoff(attempt)
    if not backoff:
        return sleep
    return backoff[min(attempt, len(backoff)) - 1]  # last entry repeats on deeper attempts


def retry(
    times: int,
    callback: Callable[[], Any],
    sleep: float = 0.0,
    *,
    backoff: Sequence[float] | Callable[[int], float] | None = None,
    when: Callable[[Exception], bool] | None = None,
) -> Any:
    """Call ``callback`` up to ``times`` times. ``backoff`` (a per-attempt sequence — last
    entry repeats — or ``attempt -> seconds`` callable) overrides ``sleep``; ``when`` limits
    which exceptions retry (others re-raise immediately). An async callback returns an
    awaitable and sleeps without blocking the loop; exhaustion re-raises the last error."""
    if inspect.iscoroutinefunction(callback):

        async def _aretry() -> Any:
            attempts = 0
            while True:
                attempts += 1
                try:
                    return await callback()
                except Exception as exc:
                    if attempts >= times or (when is not None and not when(exc)):
                        raise
                    delay = _retry_delay(attempts, sleep, backoff)
                    if delay:
                        await Sleep.asleep(delay)

        return _aretry()
    attempts = 0
    while True:
        attempts += 1
        try:
            return callback()
        except Exception as exc:
            if attempts >= times or (when is not None and not when(exc)):
                raise
            delay = _retry_delay(attempts, sleep, backoff)
            if delay:
                Sleep.sleep(delay)


class Arr:
    """Array/dict helpers (dot-aware)."""

    @staticmethod
    def get(target: Any, key: str, default: Any = None) -> Any:
        return data_get(target, key, default)

    @staticmethod
    def set(target: Any, key: str, item: Any) -> Any:
        return data_set(target, key, item)

    @staticmethod
    def has(target: Any, key: str) -> bool:
        return data_get(target, key, _MISSING) is not _MISSING

    @staticmethod
    def first(
        items: Iterable[Any], predicate: Callable[[Any], bool] | None = None, default: Any = None
    ) -> Any:
        for item in items:
            if predicate is None or predicate(item):
                return item
        return value(default)

    @staticmethod
    def last(
        items: Iterable[Any], predicate: Callable[[Any], bool] | None = None, default: Any = None
    ) -> Any:
        found = _MISSING
        for item in items:
            if predicate is None or predicate(item):
                found = item
        return found if found is not _MISSING else value(default)

    @staticmethod
    def pluck(items: Iterable[Any], key: str) -> list[Any]:
        return [data_get(item, key) for item in items]

    @staticmethod
    def flatten(items: Iterable[Any], depth: int = 32) -> list[Any]:
        result: list[Any] = []
        for item in items:
            if isinstance(item, (list, tuple)) and depth > 0:
                result.extend(Arr.flatten(cast("Iterable[Any]", item), depth - 1))
            else:
                result.append(item)
        return result

    @staticmethod
    def only(target: dict[str, Any], keys: Iterable[str]) -> dict[str, Any]:
        keyset = set(keys)
        return {k: v for k, v in target.items() if k in keyset}

    @staticmethod
    def excluding(target: dict[str, Any], keys: Iterable[str]) -> dict[str, Any]:
        keyset = set(keys)
        return {k: v for k, v in target.items() if k not in keyset}

    @staticmethod
    def wrap(obj: Any) -> list[Any]:
        if obj is None:
            return []
        return cast("list[Any]", obj) if isinstance(obj, list) else [obj]

    # --- keys / membership -------------------------------------------------
    @staticmethod
    def except_(target: dict[str, Any], keys: Iterable[str]) -> dict[str, Any]:
        """``Arr::except`` — alias of ``excluding``."""
        return Arr.excluding(target, keys)

    @staticmethod
    def exists(target: dict[str, Any], key: str) -> bool:
        """Plain (non-dot) key membership — ``Arr::exists``."""
        return key in target

    @staticmethod
    def add(target: dict[str, Any], key: str, item: Any) -> dict[str, Any]:
        """Set ``key`` (dot-aware) only if it's missing/None — ``Arr::add``."""
        existing = data_get(target, key, _MISSING)
        if existing is _MISSING or existing is None:
            data_set(target, key, item)
        return target

    @staticmethod
    def forget(target: dict[str, Any], keys: str | Iterable[str]) -> dict[str, Any]:
        """Remove one or more dot-keys in place — ``Arr::forget``."""
        key_list = [keys] if isinstance(keys, str) else list(keys)
        for key in key_list:
            parts = key.split(".")
            node: Any = target
            for part in parts[:-1]:
                if not isinstance(node, dict):
                    node = None
                    break
                node = cast("dict[str, Any]", node).get(part)
            if isinstance(node, dict):
                cast("dict[str, Any]", node).pop(parts[-1], None)
        return target

    @staticmethod
    def keys(target: dict[str, Any]) -> list[Any]:
        return list(target.keys())

    @staticmethod
    def values(target: Any) -> list[Any]:
        if isinstance(target, dict):
            return list(cast("dict[Any, Any]", target).values())
        return list(target)

    @staticmethod
    def divide(target: dict[str, Any]) -> tuple[list[Any], list[Any]]:
        """``(keys, values)`` — ``Arr::divide``."""
        return list(target.keys()), list(target.values())

    # --- shape ------------------------------------------------------------
    @staticmethod
    def is_assoc(target: Any) -> bool:
        return isinstance(target, dict)

    @staticmethod
    def is_list(target: Any) -> bool:
        return isinstance(target, (list, tuple))

    @staticmethod
    def dot(target: dict[str, Any], prepend: str = "") -> dict[str, Any]:
        """Flatten a nested dict into a single dot-keyed dict — ``Arr::dot``."""
        result: dict[str, Any] = {}
        for key, item in target.items():
            if isinstance(item, dict) and item:
                result.update(Arr.dot(cast("dict[str, Any]", item), f"{prepend}{key}."))
            else:
                result[f"{prepend}{key}"] = item
        return result

    @staticmethod
    def undot(target: dict[str, Any]) -> dict[str, Any]:
        """Expand a dot-keyed dict back into a nested dict — ``Arr::undot``."""
        result: dict[str, Any] = {}
        for key, item in target.items():
            data_set(result, key, item)
        return result

    @staticmethod
    def collapse(items: Iterable[Any]) -> list[Any]:
        """Collapse a list of lists into a single list — ``Arr::collapse``."""
        result: list[Any] = []
        for item in items:
            if isinstance(item, (list, tuple)):
                result.extend(cast("Iterable[Any]", item))
        return result

    # --- transform / order ------------------------------------------------
    @staticmethod
    def where(target: Any, predicate: Callable[[Any], bool]) -> Any:
        """Filter by a value predicate, preserving dict keys / list order — ``Arr::where``
        (the predicate here takes the value only, not the ``($value, $key)``)."""
        if isinstance(target, dict):
            return {k: v for k, v in cast("dict[Any, Any]", target).items() if predicate(v)}
        return [v for v in target if predicate(v)]

    @staticmethod
    def where_not_null(target: Any) -> Any:
        """Drop entries whose value is ``None``, preserving keys/order — ``Arr::whereNotNull``."""
        return Arr.where(target, lambda value: value is not None)

    @staticmethod
    def pull(target: dict[str, Any], key: str, default: Any = None) -> Any:
        """Read a dot-key's value then remove it in place — ``Arr::pull``."""
        value = data_get(target, key, default)
        Arr.forget(target, key)
        return value

    @staticmethod
    def has_any(target: Any, keys: str | Iterable[str]) -> bool:
        """Whether ANY of the dot-keys is present — ``Arr::hasAny``."""
        key_list = [keys] if isinstance(keys, str) else list(keys)
        return any(data_get(target, key, _MISSING) is not _MISSING for key in key_list)

    @staticmethod
    def map_with_keys(
        items: Iterable[Any], callback: Callable[[Any], tuple[Any, Any]]
    ) -> dict[Any, Any]:
        return dict(callback(item) for item in items)

    @staticmethod
    def prepend(items: Iterable[Any], item: Any) -> list[Any]:
        return [item, *items]

    @staticmethod
    def sort(items: Iterable[Any], *, reverse: bool = False) -> list[Any]:
        return sorted(items, reverse=reverse)

    @staticmethod
    def sort_desc(items: Iterable[Any]) -> list[Any]:
        return sorted(items, reverse=True)

    @staticmethod
    def take(items: Iterable[Any], limit: int) -> list[Any]:
        """First ``limit`` items, or the last ``-limit`` when negative — ``Arr::take``."""
        seq = list(items)
        return seq[:limit] if limit >= 0 else seq[limit:]

    @staticmethod
    def join(items: Iterable[Any], glue: str, final_glue: str = "") -> str:
        """Join with ``glue``; if ``final_glue`` is set, the last item uses it — ``Arr::join``."""
        parts = [str(x) for x in items]
        if not final_glue or len(parts) < 2:
            return glue.join(parts)
        return glue.join(parts[:-1]) + final_glue + parts[-1]

    @staticmethod
    def random(items: Iterable[Any], number: int | None = None) -> Any:
        """A random element, or a list of ``number`` distinct elements — ``Arr::random``.
        Uses ``secrets`` for selection (strong randomness; a superset of the needs)."""
        import secrets

        pool = list(items)
        if number is None:
            return secrets.choice(pool) if pool else None
        if number > len(pool):
            raise ValueError(f"requested {number} items but only {len(pool)} available")
        return [pool.pop(secrets.randbelow(len(pool))) for _ in range(number)]


def cache() -> Any:
    """The default cache driver, so you ``await cache().get("k")`` / ``await cache().put("k", v)``
    instead of building ``CacheManager().driver()`` by hand. Resolves the app-bound ``CacheManager``
    from the container.

    Imported as ``from arvel.support import cache`` — the bare top-level name ``arvel.cache`` is the
    cache *package*, so the helper lives here to avoid shadowing it.

    Requires a booted application with the ``CacheServiceProvider`` registered. ``support`` is a leaf
    that must not import the ``cache`` capability (DR-0026), so there is no app-less fallback — the
    cache is reached only through the container.
    """
    from arvel.kernel.globals import app, has_application

    if not (has_application() and app().bound("cache")):
        raise RuntimeError(
            "cache() requires a booted application with the CacheServiceProvider registered. "
            "Build the cache directly (arvel.cache.CacheManager) outside an application context."
        )
    return app().make("cache").driver()
