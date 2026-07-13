"""arvel.support.facades — static-looking proxies to container-resolved services.

``Facade`` forwards missing class attributes (via ``FacadeMeta.__getattr__``, the
Python equivalent of PHP ``__callStatic``) to the object resolved from the current
application's container under the facade's ``accessor()`` key. Async methods stay
awaitable (we forward the bound method untouched). Roots resolve dynamically from
the current app, so swapping the app (tests) is reflected immediately; ``swap()``/
``fake()`` override a root for tests.

Type-checkers can't see through ``__getattr__`` — each facade ships a ``.pyi`` stub
(generated in CI from the underlying typed class; see doc 06). Grounded in
knowledge/port/06-facades.md.
"""

from __future__ import annotations

from typing import Any, ClassVar


class FacadeMeta(type):
    def __getattr__(cls, name: str) -> Any:
        return getattr(cls._resolve_root(), name)


class Facade(metaclass=FacadeMeta):
    """Base facade. Subclasses define ``accessor()`` (and optionally ``fake_class()``)."""

    _swapped: ClassVar[dict[str, Any]] = {}

    @classmethod
    def accessor(cls) -> str:
        raise NotImplementedError(f"{cls.__name__} must define accessor()")

    @classmethod
    def _resolve_root(cls) -> Any:
        key = cls.accessor()
        if key in cls._swapped:
            return cls._swapped[key]
        from arvel.kernel.globals import app

        return app(key)

    @classmethod
    def swap(cls, instance: Any) -> Any:
        """Replace the resolved root (tests)."""
        cls._swapped[cls.accessor()] = instance
        return instance

    @classmethod
    def fake(cls) -> Any:
        """Swap in a fresh fake implementation (tests)."""
        return cls.swap(cls.fake_class()())

    @classmethod
    def fake_class(cls) -> type:
        raise NotImplementedError(f"{cls.__name__} has no fake_class()")

    @classmethod
    def clear_swapped(cls) -> None:
        cls._swapped.clear()


def set_application(app: Any) -> None:
    """Reset facade root overrides on (re)boot. Roots themselves resolve dynamically
    from the current application set via ``arvel.kernel.set_application``."""
    Facade.clear_swapped()


class Config(Facade):
    @classmethod
    def accessor(cls) -> str:
        return "config"


class Log(Facade):
    @classmethod
    def accessor(cls) -> str:
        return "log"


class Event(Facade):
    @classmethod
    def accessor(cls) -> str:
        return "events"


class Hash(Facade):
    @classmethod
    def accessor(cls) -> str:
        return "hash"


class Crypt(Facade):
    @classmethod
    def accessor(cls) -> str:
        return "encrypter"


class Http(Facade):
    @classmethod
    def accessor(cls) -> str:
        return "http"

    @classmethod
    def fake(cls, mapping: Any = None) -> Any:
        """``Http.fake({...})`` overrides the generic ``Facade.fake()`` (which takes no args and
        swaps in a ``fake_class()`` instance) — the HTTP fake takes a URL-pattern → stub mapping
        and swaps the client's transport instead. See ``arvel.client.Client.fake``."""
        return cls._resolve_root().fake(mapping)


class Route(Facade):
    @classmethod
    def accessor(cls) -> str:
        return "router"


class DB(Facade):
    @classmethod
    def accessor(cls) -> str:
        return "db"


class Lang(Facade):
    @classmethod
    def accessor(cls) -> str:
        return "translator"


class Cache(Facade):
    @classmethod
    def accessor(cls) -> str:
        return "cache"


class Redis(Facade):
    """Direct Redis access — distinct from
    ``Cache``, which goes through the cashews cache abstraction."""

    @classmethod
    def accessor(cls) -> str:
        return "redis"


class Storage(Facade):
    @classmethod
    def accessor(cls) -> str:
        return "filesystem"


class Mail(Facade):
    @classmethod
    def accessor(cls) -> str:
        return "mail"


class View(Facade):
    @classmethod
    def accessor(cls) -> str:
        return "view"


class Queue(Facade):
    @classmethod
    def accessor(cls) -> str:
        return "queue"


class Schedule(Facade):
    """The task scheduler — define cron-cadenced work (``Schedule.command(...).daily()``,
    ``Schedule.job(...).hourly()``, ``Schedule.call(fn).cron(...)``) in ``routes/console.py``;
    ``arvel schedule:run`` (a once-a-minute cron entry) runs what's due."""

    @classmethod
    def accessor(cls) -> str:
        return "schedule"


class Auth(Facade):
    @classmethod
    def accessor(cls) -> str:
        return "auth"


class Gate(Facade):
    @classmethod
    def accessor(cls) -> str:
        return "gate"


class Date(Facade):
    @classmethod
    def accessor(cls) -> str:
        return "date"


class Validator(Facade):
    @classmethod
    def accessor(cls) -> str:
        return "validator"


class RateLimiter(Facade):
    """Named, cache-backed rate limiters (``arvel.http.rate_limiter.RateLimiter``) — register a
    limiter's rule with ``RateLimiter.for_("api", resolver)``, consumed by the ``throttle:api``
    route middleware. Bound as ``limiter`` by the served ``HttpKernel`` (over the app's cache)."""

    @classmethod
    def accessor(cls) -> str:
        return "limiter"


__all__ = [
    "DB",
    "Auth",
    "Cache",
    "Config",
    "Crypt",
    "Date",
    "Event",
    "Facade",
    "FacadeMeta",
    "Gate",
    "Hash",
    "Http",
    "Lang",
    "Log",
    "Mail",
    "Queue",
    "RateLimiter",
    "Redis",
    "Route",
    "Storage",
    "Validator",
    "View",
    "set_application",
]
