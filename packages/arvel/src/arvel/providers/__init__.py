"""Service providers — the two-pass bootstrap unit.

Re-exports are lazy (PEP 562). Eagerly importing ``http_provider`` here created a
cycle: ``routing`` imports ``providers.service_provider`` (which runs this init),
and ``http_provider`` imports ``Router`` back from ``routing``. The old eager
root ``__init__`` masked it by import ordering; lazy loading breaks it for real.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arvel.providers.broadcast_provider import BroadcastServiceProvider
    from arvel.providers.config_provider import ConfigServiceProvider
    from arvel.providers.database_provider import DatabaseServiceProvider
    from arvel.providers.http_provider import HttpServiceProvider
    from arvel.providers.lang_provider import LangServiceProvider
    from arvel.providers.log_provider import LogServiceProvider
    from arvel.providers.scheduler_provider import SchedulerServiceProvider
    from arvel.providers.service_provider import ServiceProvider

_LAZY_EXPORTS: dict[str, str] = {
    "BroadcastServiceProvider": "arvel.providers.broadcast_provider",
    "ConfigServiceProvider": "arvel.providers.config_provider",
    "DatabaseServiceProvider": "arvel.providers.database_provider",
    "HttpServiceProvider": "arvel.providers.http_provider",
    "LangServiceProvider": "arvel.providers.lang_provider",
    "LogServiceProvider": "arvel.providers.log_provider",
    "SchedulerServiceProvider": "arvel.providers.scheduler_provider",
    "ServiceProvider": "arvel.providers.service_provider",
}


def __getattr__(name: str) -> object:
    module = _LAZY_EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(module), name)


def __dir__() -> list[str]:
    return sorted(__all__)


__all__ = [
    "BroadcastServiceProvider",
    "ConfigServiceProvider",
    "DatabaseServiceProvider",
    "HttpServiceProvider",
    "LangServiceProvider",
    "LogServiceProvider",
    "SchedulerServiceProvider",
    "ServiceProvider",
]
