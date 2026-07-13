"""arvel — a production-grade web framework for Python.

This top-level package is deliberately *light*: importing ``arvel`` must pull in
**zero** heavy third-party libraries (Litestar, SQLAlchemy, taskiq, Pillow, …).
Public names are resolved lazily through a module-level ``__getattr__`` (PEP 562)
so that, e.g., ``from arvel import Model`` imports :mod:`arvel.database` only when
``Model`` is first *used* — never on ``import arvel``.

Capability stories append their public exports to ``_LAZY`` as they land; see
``knowledge/port/00-porting-strategy.md`` §5b (startup NFR) and DR-0002/DR-0003.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

__version__ = "0.63.4"  # x-release-please-version

# name -> (submodule, attribute), resolved lazily by __getattr__ below.
_LAZY: dict[str, tuple[str, str]] = {
    "Application": ("arvel.kernel", "Application"),
    "ApplicationBuilder": ("arvel.kernel", "ApplicationBuilder"),
    "Container": ("arvel.kernel", "Container"),
    "ServiceProvider": ("arvel.kernel", "ServiceProvider"),
    "app": ("arvel.kernel", "app"),
    "config": ("arvel.kernel", "config"),
    "env": ("arvel.kernel", "env"),
    "Settings": ("arvel.kernel", "Settings"),
    "Collection": ("arvel.support", "Collection"),
    "Str": ("arvel.support", "Str"),
    "Config": ("arvel.support.facades", "Config"),
    "Console": ("arvel.console.closure", "Console"),
    "Log": ("arvel.support.facades", "Log"),
    "Event": ("arvel.support.facades", "Event"),
    "Hash": ("arvel.support.facades", "Hash"),
    "Crypt": ("arvel.support.facades", "Crypt"),
    "Http": ("arvel.support.facades", "Http"),
    "Route": ("arvel.support.facades", "Route"),
    "Date": ("arvel.dates", "Date"),
    "now": ("arvel.dates", "now"),
    "Model": ("arvel.database", "Model"),
    "Attribute": ("arvel.database", "Attribute"),
    "raw": ("arvel.database", "raw"),
    "scope": ("arvel.database", "scope"),
    "DB": ("arvel.support.facades", "DB"),
    "Lang": ("arvel.support.facades", "Lang"),
    "Cache": ("arvel.support.facades", "Cache"),
    "Storage": ("arvel.support.facades", "Storage"),
    "Mail": ("arvel.support.facades", "Mail"),
    "Mailable": ("arvel.mail", "Mailable"),
    "Notification": ("arvel.notifications", "Notification"),
    "Notifiable": ("arvel.notifications", "Notifiable"),
    "view": ("arvel.views", "view"),
    "cached": ("arvel.cache", "cached"),
    "abort": ("arvel.http", "abort"),
    "response": ("arvel.http", "response"),
    "redirect": ("arvel.http", "redirect"),
    "url": ("arvel.routing", "url"),
    "route": ("arvel.routing", "route"),
    "to_route": ("arvel.routing", "to_route"),
    "Schema": ("arvel.validation", "Schema"),
    "validate": ("arvel.validation", "validate"),
    "FormRequest": ("arvel.validation", "FormRequest"),
    "View": ("arvel.support.facades", "View"),
    "Job": ("arvel.queue", "Job"),
    "Queue": ("arvel.support.facades", "Queue"),
    "Schedule": ("arvel.support.facades", "Schedule"),
    "Validator": ("arvel.support.facades", "Validator"),
    "Auth": ("arvel.support.facades", "Auth"),
    "Gate": ("arvel.support.facades", "Gate"),
    "Authenticatable": ("arvel.auth", "Authenticatable"),
    "Image": ("arvel.media", "Image"),
    "Video": ("arvel.media", "Video"),
    "today": ("arvel.dates", "today"),
    "trans": ("arvel.localization", "trans"),
    "trans_choice": ("arvel.localization", "trans_choice"),
    "LengthAwarePaginator": ("arvel.pagination", "LengthAwarePaginator"),
    "Paginator": ("arvel.pagination", "Paginator"),
    # global helper functions (arvel.support.helpers, re-exported by arvel.support)
    "dd": ("arvel.support", "dd"),
    "dump": ("arvel.support", "dump"),
    "base_path": ("arvel.support", "base_path"),
    "app_path": ("arvel.support", "app_path"),
    "storage_path": ("arvel.support", "storage_path"),
    "public_path": ("arvel.support", "public_path"),
    "resource_path": ("arvel.support", "resource_path"),
    "database_path": ("arvel.support", "database_path"),
    "config_path": ("arvel.support", "config_path"),
    "lang_path": ("arvel.support", "lang_path"),
    "abort_if": ("arvel.http.helpers", "abort_if"),
    "abort_unless": ("arvel.http.helpers", "abort_unless"),
    "report": ("arvel.support", "report"),
    "report_if": ("arvel.support", "report_if"),
    "report_unless": ("arvel.support", "report_unless"),
    "transform": ("arvel.support", "transform"),
    "collect": ("arvel.support", "collect"),
    "resolve": ("arvel.support", "resolve"),
    "event": ("arvel.support", "event"),
    "info": ("arvel.support", "info"),
    "logger": ("arvel.support", "logger"),
    "bcrypt": ("arvel.support", "bcrypt"),
    "encrypt": ("arvel.support", "encrypt"),
    "decrypt": ("arvel.support", "decrypt"),
    "validator": ("arvel.support", "validator"),
    "policy": ("arvel.support", "policy"),
    "request": ("arvel.http.helpers", "request"),
    "session": ("arvel.http.helpers", "session"),
    "cookie": ("arvel.http.helpers", "cookie"),
    "old": ("arvel.http.helpers", "old"),
    "class_basename": ("arvel.support", "class_basename"),
    "enum_value": ("arvel.support", "enum_value"),
    "literal": ("arvel.support", "literal"),
    "noop": ("arvel.support", "noop"),
    "windows_os": ("arvel.support", "windows_os"),
}

# Kept static (pyright requires a literal) and in sync with _LAZY.
__all__ = [
    "DB",
    "Application",
    "ApplicationBuilder",
    "Attribute",
    "Auth",
    "Authenticatable",
    "Cache",
    "Collection",
    "Config",
    "Console",
    "Container",
    "Crypt",
    "Date",
    "Event",
    "FormRequest",
    "Gate",
    "Hash",
    "Http",
    "Image",
    "Job",
    "Lang",
    "LengthAwarePaginator",
    "Log",
    "Mail",
    "Mailable",
    "Model",
    "Notifiable",
    "Notification",
    "Paginator",
    "Queue",
    "Route",
    "Schedule",
    "Schema",
    "ServiceProvider",
    "Settings",
    "Storage",
    "Str",
    "Validator",
    "Video",
    "View",
    "__version__",
    "abort",
    "abort_if",
    "abort_unless",
    "app",
    "app_path",
    "base_path",
    "bcrypt",
    "cached",
    "class_basename",
    "collect",
    "config",
    "config_path",
    "cookie",
    "database_path",
    "dd",
    "decrypt",
    "dump",
    "encrypt",
    "enum_value",
    "env",
    "event",
    "info",
    "lang_path",
    "literal",
    "logger",
    "noop",
    "now",
    "old",
    "policy",
    "public_path",
    "raw",
    "redirect",
    "report",
    "report_if",
    "report_unless",
    "request",
    "resolve",
    "resource_path",
    "response",
    "route",
    "scope",
    "session",
    "storage_path",
    "to_route",
    "today",
    "trans",
    "trans_choice",
    "transform",
    "url",
    "validate",
    "validator",
    "view",
    "windows_os",
]


def __getattr__(name: str) -> object:
    """Lazily import a public export the first time it is accessed (PEP 562)."""
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = target
    value = getattr(importlib.import_module(module_name), attr)
    globals()[name] = value  # cache so subsequent access skips __getattr__
    return value


def __dir__() -> list[str]:
    return sorted(__all__)


if TYPE_CHECKING:  # give type-checkers + IDEs the real symbols for the lazy surface
    from arvel.auth import Authenticatable
    from arvel.cache import cached
    from arvel.console.closure import Console
    from arvel.database import Attribute, Model, raw, scope
    from arvel.dates import Date, now, today
    from arvel.http import abort
    from arvel.http.helpers import abort_if, abort_unless, cookie, old, request, session
    from arvel.http.redirect import redirect
    from arvel.http.response import response
    from arvel.kernel import (
        Application,
        ApplicationBuilder,
        Container,
        ServiceProvider,
        Settings,
        app,
        config,
        env,
    )
    from arvel.localization import trans, trans_choice
    from arvel.mail import Mailable
    from arvel.media import Image, Video
    from arvel.notifications import Notifiable, Notification
    from arvel.pagination import LengthAwarePaginator, Paginator
    from arvel.queue import Job
    from arvel.routing import route, to_route, url
    from arvel.support import (
        Collection,
        Str,
        app_path,
        base_path,
        bcrypt,
        class_basename,
        collect,
        config_path,
        database_path,
        dd,
        decrypt,
        dump,
        encrypt,
        enum_value,
        event,
        info,
        lang_path,
        literal,
        logger,
        noop,
        policy,
        public_path,
        report,
        report_if,
        report_unless,
        resolve,
        resource_path,
        storage_path,
        transform,
        validator,
        windows_os,
    )
    from arvel.support.facades import (
        DB,
        Auth,
        Cache,
        Config,
        Crypt,
        Event,
        Gate,
        Hash,
        Http,
        Lang,
        Log,
        Mail,
        Queue,
        Route,
        Schedule,
        Storage,
        Validator,
        View,
    )
    from arvel.validation import FormRequest, Schema, validate
    from arvel.views import view
