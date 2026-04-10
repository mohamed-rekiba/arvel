"""QueueManager — factory that resolves the configured queue driver."""

from __future__ import annotations

from collections.abc import Callable

from arvel.foundation.exceptions import ConfigurationError
from arvel.queue.config import QueueSettings
from arvel.queue.contracts import QueueContract
from arvel.queue.drivers.null_driver import NullQueue
from arvel.queue.drivers.sync_driver import SyncQueue

DriverFactory = Callable[..., QueueContract]

_BUILTIN_DRIVERS: dict[str, Callable[[QueueSettings], QueueContract]] = {
    "sync": lambda _settings: SyncQueue(),
    "null": lambda _settings: NullQueue(),
    "taskiq": lambda settings: _make_taskiq(settings),
}


def _make_taskiq(settings: QueueSettings) -> QueueContract:
    from arvel.queue.drivers.taskiq_driver import TaskiqQueue

    effective_url = settings.taskiq_url if settings.taskiq_url else settings.redis_url
    return TaskiqQueue(broker_type=settings.taskiq_broker, url=effective_url)


class QueueManager:
    """Resolves the configured :class:`QueueContract` implementation.

    Uses ``QueueSettings.driver`` to pick from built-in drivers
    (``sync``, ``null``, ``taskiq``) or custom-registered ones.
    """

    def __init__(self) -> None:
        self._custom_drivers: dict[str, Callable[..., QueueContract]] = {}

    def register_driver(self, name: str, factory: Callable[..., QueueContract]) -> None:
        """Register a custom driver factory by name."""
        self._custom_drivers[name] = factory

    def create_driver(self, settings: QueueSettings | None = None) -> QueueContract:
        """Build and return the queue driver specified by *settings*."""
        if settings is None:
            settings = QueueSettings()

        name = settings.driver

        if name in self._custom_drivers:
            return self._custom_drivers[name]()

        if name in _BUILTIN_DRIVERS:
            return _BUILTIN_DRIVERS[name](settings)

        available = sorted({*_BUILTIN_DRIVERS, *self._custom_drivers})
        raise ConfigurationError(
            f"Unknown queue driver {name!r}. Available: {', '.join(available)}"
        )
