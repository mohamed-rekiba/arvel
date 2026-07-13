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


def app_url(path: str = "") -> str:
    """Join ``path`` onto ``config('app.url')`` — the one absolute-URL joiner every call site
    (``routing._absolute``, ``views._url``) delegates to (H16). Reproduces the shared logic
    byte-for-byte: the base is ``config('app.url')`` when a bound app has one, else ``""``,
    stripped of a trailing slash; ``path`` is prefixed with a single leading slash (empty stays
    empty); an empty result joins to ``"/"``."""
    from arvel.kernel.globals import app, has_application

    base = ""
    if has_application() and app().bound("config"):
        base = str(app("config").get("app.url", "") or "")
    base = base.rstrip("/")
    suffix = ("/" + path.lstrip("/")) if path else ""
    return (base + suffix) if base else (suffix or "/")


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


# =============================================================================
# Global helper functions — the lowercase shorthands over the framework's
# facades/objects (grounded in knowledge/port/06-facades.md §helpers). Heavy
# imports stay function-local so ``import arvel`` remains light (DR-0002/0003).
# =============================================================================


# --- debug: dump / dump-and-die ----------------------------------------------
def dump(*args: Any) -> Any:
    """Pretty-print each argument and return them — ``dump(x)`` returns ``x`` and ``dump(a, b)``
    the tuple, so it drops into an expression without breaking the flow. The dump-and-continue
    sibling of :func:`dd`. Uses stdlib ``pprint`` (``support`` is a leaf — no ``rich`` dependency);
    objects render through their ``__repr__`` (models show their columns)."""
    from pprint import pprint

    for arg in args:
        pprint(arg)
    return args[0] if len(args) == 1 else args


def _in_interactive_shell() -> bool:
    """Whether we're inside an interactive REPL — arvel's ``shell`` on IPython, or the stdlib
    REPL / ``python -i`` (which set ``sys.ps1``). There ``dd`` stops the statement rather than
    killing the whole session. Reached via importlib since IPython ships no type stubs (as in
    ``console.shell``)."""
    import importlib
    import sys

    try:
        ipython: Any = importlib.import_module("IPython")
    except ImportError:
        return hasattr(sys, "ps1")
    return ipython.get_ipython() is not None or hasattr(sys, "ps1")


class DumpDie(Exception):
    """Raised by :func:`dd` to stop the current unit of work after dumping. Deliberately an
    ``Exception`` — **not** ``SystemExit`` — so it flows through the framework's normal exception
    handling: inside a request it renders as a (debug) response and ends *that request only*, never
    the server worker; the CLI entrypoint catches it for a clean non-zero exit. In an interactive
    shell :func:`dd` returns instead of raising. ``sys.exit`` would be wrong here — its
    ``SystemExit`` is a ``BaseException`` that slips past every ``except Exception`` handler and
    escapes to the ASGI server."""


def dd(*args: Any) -> None:
    """Dump and die — pretty-print the arguments (see :func:`dump`) then stop the current unit of
    work. Inside an interactive shell it dumps and returns (your session survives); everywhere else
    it raises :class:`DumpDie`, which the request pipeline renders as a response and the CLI turns
    into a clean exit — so it never kills a long-running server."""
    dump(*args)
    if _in_interactive_shell():
        return
    raise DumpDie(", ".join(repr(arg) for arg in args) or "dd()")


# --- filesystem paths (joined onto the application root) ----------------------
def _app_base() -> str:
    from arvel.kernel.globals import app, has_application

    return str(app().base_path) if has_application() else "."


def _project_path(segment: str, path: str) -> str:
    """``{base}/{segment}[/{path}]`` — the shared join every path helper below routes through."""
    import os.path

    root = os.path.join(_app_base(), segment) if segment else _app_base()
    return os.path.join(root, path) if path else root


def base_path(path: str = "") -> str:
    """The application root directory, with ``path`` joined on."""
    return _project_path("", path)


def app_path(path: str = "") -> str:
    """The ``app/`` directory (application code), with ``path`` joined on."""
    return _project_path("app", path)


def storage_path(path: str = "") -> str:
    """The ``storage/`` directory (logs, caches, uploads), with ``path`` joined on."""
    return _project_path("storage", path)


def public_path(path: str = "") -> str:
    """The ``public/`` directory (web-served assets), with ``path`` joined on."""
    return _project_path("public", path)


def resource_path(path: str = "") -> str:
    """The ``resources/`` directory (views, un-compiled assets), with ``path`` joined on."""
    return _project_path("resources", path)


def database_path(path: str = "") -> str:
    """The ``database/`` directory (migrations, seeders, sqlite files), with ``path`` joined on."""
    return _project_path("database", path)


def config_path(path: str = "") -> str:
    """The config directory (the ``with_config_dir`` override, else ``{base}/config``)."""
    import os.path

    from arvel.kernel.globals import app, has_application

    directory = getattr(app(), "config_dir", None) if has_application() else None
    root = directory or _project_path("config", "")
    return os.path.join(root, path) if path else root


def lang_path(path: str = "") -> str:
    """The translations directory (the ``with_lang_dir`` override, else ``{base}/lang``)."""
    import os.path

    from arvel.kernel.globals import app, has_application

    directory = getattr(app(), "lang_dir", None) if has_application() else None
    root = directory or _project_path("lang", "")
    return os.path.join(root, path) if path else root


# NOTE: the http-touching helpers (abort_if/abort_unless and the per-request accessors
# request/session/cookie/old) live in ``arvel.http.helpers`` — ``support`` is a leaf and must not
# import ``arvel.http`` (import-linter). They're re-exported on the top-level ``arvel`` surface.


# --- report ------------------------------------------------------------------
def report(exc: BaseException) -> None:
    """Send ``exc`` to the bound ExceptionHandler without raising it — fire-and-forget logging
    of a caught error. No-op when no application is bound; never raises."""
    _report_to_handler(exc)


def report_if(condition: Any, exc: BaseException) -> Any:
    """:func:`report` ``exc`` when ``condition`` is truthy; return ``condition``."""
    if condition:
        _report_to_handler(exc)
    return condition


def report_unless(condition: Any, exc: BaseException) -> Any:
    """:func:`report` ``exc`` when ``condition`` is falsy; return ``condition``."""
    if not condition:
        _report_to_handler(exc)
    return condition


def transform(val: Any, callback: Callable[[Any], Any], default: Any = None) -> Any:
    """Run ``callback(val)`` when ``val`` is :func:`filled`; otherwise return ``default``
    (resolved if callable). The value-piping sibling of :func:`optional`."""
    if filled(val):
        return callback(val)
    return value(default)


# --- shorthands over existing facades / objects ------------------------------
def collect(items: Any = None) -> Any:
    """Wrap ``items`` in a :class:`~arvel.support.Collection` — ``collect([1, 2, 3])``."""
    from arvel.support import Collection

    return Collection([] if items is None else items)


def resolve(abstract: Any) -> Any:
    """Resolve ``abstract`` out of the container — alias of ``app(abstract)``."""
    from arvel.kernel.globals import app

    return app(abstract)


def event(evt: Any, *payload: Any) -> Any:
    """Dispatch ``evt`` through the event bus — ``Event.dispatch`` shorthand."""
    from arvel.support.facades import Event

    return Event.dispatch(evt, *payload)


def info(message: str, **context: Any) -> None:
    """Log an info-level line — ``Log.info`` shorthand."""
    from arvel.support.facades import Log

    Log.info(message, **context)


def logger(message: str | None = None, **context: Any) -> Any:
    """With a ``message``, log it at debug level; with none, return the ``Log`` facade to chain on."""
    from arvel.support.facades import Log

    if message is None:
        return Log
    Log.debug(message, **context)
    return None


def bcrypt(plain: str) -> str:
    """Hash ``plain`` with the **bcrypt** driver — as the name says. For the app's configured default
    hasher (Argon2id unless changed), use ``Hash.make`` / the ``hashed`` model cast instead."""
    from arvel.security import Hasher

    return Hasher(driver="bcrypt").make(plain)


def encrypt(val: Any) -> Any:
    """Encrypt ``val`` with the app key — ``Crypt.encrypt`` shorthand."""
    from arvel.support.facades import Crypt

    return Crypt.encrypt(val)


def decrypt(token: Any) -> Any:
    """Decrypt a ``Crypt``-issued ``token`` — ``Crypt.decrypt`` shorthand."""
    from arvel.support.facades import Crypt

    return Crypt.decrypt(token)


def validator(data: Any, rules: Any, messages: Any = None, **kwargs: Any) -> Any:
    """Build a validator — ``Validator.make`` shorthand."""
    from arvel.support.facades import Validator

    if messages is None:
        return Validator.make(data, rules, **kwargs)
    return Validator.make(data, rules, messages, **kwargs)


def policy(model: Any) -> Any:
    """The policy instance registered for ``model`` — ``Gate.resolve_policy`` shorthand."""
    from arvel.support.facades import Gate

    return Gate.resolve_policy(model)


# --- small pure utilities ----------------------------------------------------
def class_basename(target: Any) -> str:
    """The class name without its module — ``class_basename(obj)`` or ``class_basename(Cls)``."""
    cls = target if isinstance(target, type) else type(target)
    return cls.__name__


def enum_value(val: Any) -> Any:
    """An enum member's ``.value``, or ``val`` unchanged when it isn't an enum member."""
    import enum

    return val.value if isinstance(val, enum.Enum) else val


def literal(**attributes: Any) -> Any:
    """An ad-hoc object with the given named attributes — ``literal(name="x", n=1).name``."""
    from types import SimpleNamespace

    return SimpleNamespace(**attributes)


def noop(*_args: Any, **_kwargs: Any) -> None:
    """Accept any arguments and do nothing — a placeholder callback."""
    return None


def windows_os() -> bool:
    """Whether the host OS is Windows."""
    import os

    return os.name == "nt"
