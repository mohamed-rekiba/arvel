"""arvel.support.manager — the driver/Strategy ``Manager`` base (Laravel ``Manager``).

One contract, a config-selected backend, and an ``extend`` seam for ecosystem
packages. The Manager does driver *dispatch* only (``create_<name>_driver`` or a
registered creator); each driver instantiates its mandated real library. A missing
backend raises ``MissingExtraError`` with the right ``uv add`` hint.
Grounded in knowledge/port/16-managers.md.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from arvel.kernel.settings import Settings

_S = TypeVar("_S", bound="Settings")


class MissingExtraError(RuntimeError):
    """Raised when a requested driver's optional dependency isn't installed."""

    def __init__(self, name: str, extra: str | None = None) -> None:
        super().__init__(f"No driver {name!r}. Install it with: uv add 'arvel[{extra or name}]'")


class Manager:
    """Base driver manager: resolves + caches drivers, forwards to the default one."""

    def __init__(self, app: Any = None) -> None:
        self.app = app
        self._drivers: dict[str, Any] = {}
        self._creators: dict[str, Any] = {}

    def default_driver(self) -> str:
        raise NotImplementedError(f"{type(self).__name__} must define default_driver()")

    def _settings(self, settings_cls: type[_S]) -> _S:
        """Construct a typed ``Settings`` reading from THIS manager's ``app`` config — so
        ``Manager(some_app)`` honors *that* app's config section, not just the global one. Falls back
        to the global config when the manager has no app (the common container-resolved case, where the
        manager's app already *is* the global app, behaves identically either way)."""
        app = self.app
        key = getattr(settings_cls, "__config_key__", None)
        if app is not None and key is not None and hasattr(app, "config"):
            return settings_cls.from_source(app.config(key))
        return settings_cls()

    def driver(self, name: str | None = None) -> Any:
        name = name or self.default_driver()
        if name not in self._drivers:
            self._drivers[name] = self._make(name)
        return self._drivers[name]

    def extend(self, name: str, creator: Any) -> Manager:
        """Register a custom driver creator (the ecosystem-extension seam)."""
        self._creators[name] = creator
        return self

    def _make(self, name: str) -> Any:
        if name in self._creators:
            return self._creators[name](self.app)
        creator = getattr(self, f"create_{name}_driver", None)
        if creator is not None:
            return creator()
        raise MissingExtraError(name)

    def __getattr__(self, item: str) -> Any:
        # Forward unknown attributes to the default driver (Cache.get -> driver().get).
        if item.startswith("_"):
            raise AttributeError(item)
        return getattr(self.driver(), item)
