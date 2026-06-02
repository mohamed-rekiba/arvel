"""Arvel — the Laravel of Python.

Public API surface for foundations and the HTTP layer. The full reference lives
at ``docs/site/docs/reference/api.md`` (published at ``/reference/api/``).
Symbols not in ``__all__`` are internal and may change without notice.

Re-exports are resolved lazily (PEP 562). Importing ``arvel`` no longer drags in
FastAPI/Starlette/SQLAlchemy — those load only when you actually touch a symbol
that needs them. This keeps the CLI fast: ``arvel --help`` and ``make:*`` don't
pay the full framework import cost.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

# Eager, but cheap (neither pulls FastAPI/SQLAlchemy/starlette). Bound here
# because their names collide with the `arvel.config` package and `arvel.dep`
# module — a lazy __getattr__ would be shadowed the moment those submodules
# import, so `from arvel import config`/`dep` would hand back the module.
from arvel.config import config
from arvel.dep import dep

if TYPE_CHECKING:
    from fastapi import FastAPI as _FastAPI
    from starlette.types import Lifespan as _StarletteLifespan

    from arvel.application import (
        Application,
        ApplicationBuilder,
        BootError,
        ShutdownError,
        serve,
    )
    from arvel.config import ConfigError, ConfigNotRegisteredError, NoPrefix
    from arvel.container import (
        AsyncBindingError,
        BindingResolutionError,
        CircularDependencyError,
        Container,
        Scope,
    )
    from arvel.http.auth import Guard, JwtGuard, SessionGuard, UserResolver
    from arvel.http.controller import Controller
    from arvel.http.exceptions import (
        AuthorizationException,
        BadRequestException,
        ConflictException,
        HttpException,
        HttpExceptionHandler,
        MethodNotAllowedException,
        NotFoundException,
        ServerErrorException,
        ThrottleException,
        UnauthenticatedException,
        ValidationException,
    )
    from arvel.http.middleware import (
        Authenticate,
        Cors,
        Middleware,
        Throttle,
        VerifyCsrf,
    )
    from arvel.http.negotiation import wants_json
    from arvel.http.ratelimit import Attempt, InMemoryStore, RateLimiterStore, RedisStore
    from arvel.http.requests import FormRequest
    from arvel.http.resources import JsonResource, ResourceCollection
    from arvel.providers import HttpServiceProvider, ServiceProvider
    from arvel.routing import URL, Route, Router, RouteServiceProvider, RoutingError, url
    from arvel.support import Arr, Str
    from arvel.support.env import env

    #: Runtime type of the framework's HTTP ASGI app (currently ``fastapi.FastAPI``).
    #: App code should reference ``arvel.ASGIApp`` rather than importing FastAPI
    #: directly, so the underlying ASGI framework stays an implementation detail.
    ASGIApp = _FastAPI
    #: Type of a lifespan callable accepted by ``Application.into_asgi(lifespan=...)``.
    HttpLifespan = _StarletteLifespan[_FastAPI]

__version__ = "0.11.0"  # x-release-please-version

# Public symbol -> module it lives in. Resolved on first access via __getattr__.
_LAZY_EXPORTS: dict[str, str] = {
    "Application": "arvel.application",
    "ApplicationBuilder": "arvel.application",
    "BootError": "arvel.application",
    "ShutdownError": "arvel.application",
    "serve": "arvel.application",
    "ConfigError": "arvel.config",
    "ConfigNotRegisteredError": "arvel.config",
    "NoPrefix": "arvel.config",
    "AsyncBindingError": "arvel.container",
    "BindingResolutionError": "arvel.container",
    "CircularDependencyError": "arvel.container",
    "Container": "arvel.container",
    "Scope": "arvel.container",
    "Guard": "arvel.http.auth",
    "JwtGuard": "arvel.http.auth",
    "SessionGuard": "arvel.http.auth",
    "UserResolver": "arvel.http.auth",
    "Controller": "arvel.http.controller",
    "AuthorizationException": "arvel.http.exceptions",
    "BadRequestException": "arvel.http.exceptions",
    "ConflictException": "arvel.http.exceptions",
    "HttpException": "arvel.http.exceptions",
    "HttpExceptionHandler": "arvel.http.exceptions",
    "MethodNotAllowedException": "arvel.http.exceptions",
    "NotFoundException": "arvel.http.exceptions",
    "ServerErrorException": "arvel.http.exceptions",
    "ThrottleException": "arvel.http.exceptions",
    "UnauthenticatedException": "arvel.http.exceptions",
    "ValidationException": "arvel.http.exceptions",
    "Authenticate": "arvel.http.middleware",
    "Cors": "arvel.http.middleware",
    "Middleware": "arvel.http.middleware",
    "Throttle": "arvel.http.middleware",
    "VerifyCsrf": "arvel.http.middleware",
    "wants_json": "arvel.http.negotiation",
    "Attempt": "arvel.http.ratelimit",
    "InMemoryStore": "arvel.http.ratelimit",
    "RateLimiterStore": "arvel.http.ratelimit",
    "RedisStore": "arvel.http.ratelimit",
    "FormRequest": "arvel.http.requests",
    "JsonResource": "arvel.http.resources",
    "ResourceCollection": "arvel.http.resources",
    "HttpServiceProvider": "arvel.providers",
    "ServiceProvider": "arvel.providers",
    "URL": "arvel.routing",
    "Route": "arvel.routing",
    "Router": "arvel.routing",
    "RouteServiceProvider": "arvel.routing",
    "RoutingError": "arvel.routing",
    "url": "arvel.routing",
    "Arr": "arvel.support",
    "Str": "arvel.support",
    "env": "arvel.support.env",
}


def __getattr__(name: str) -> object:
    """Resolve public re-exports lazily so importing ``arvel`` stays cheap."""
    module = _LAZY_EXPORTS.get(name)
    if module is not None:
        return getattr(importlib.import_module(module), name)
    if name == "ASGIApp":
        return importlib.import_module("fastapi").FastAPI
    if name == "HttpLifespan":
        lifespan = importlib.import_module("starlette.types").Lifespan
        fastapi_app = importlib.import_module("fastapi").FastAPI
        return lifespan[fastapi_app]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)


__all__ = [
    "URL",
    "ASGIApp",
    "Application",
    "ApplicationBuilder",
    "Arr",
    "AsyncBindingError",
    "Attempt",
    "Authenticate",
    "AuthorizationException",
    "BadRequestException",
    "BindingResolutionError",
    "BootError",
    "CircularDependencyError",
    "ConfigError",
    "ConfigNotRegisteredError",
    "ConflictException",
    "Container",
    "Controller",
    "Cors",
    "FormRequest",
    "Guard",
    "HttpException",
    "HttpExceptionHandler",
    "HttpLifespan",
    "HttpServiceProvider",
    "InMemoryStore",
    "JsonResource",
    "JwtGuard",
    "MethodNotAllowedException",
    "Middleware",
    "NoPrefix",
    "NotFoundException",
    "RateLimiterStore",
    "RedisStore",
    "ResourceCollection",
    "Route",
    "RouteServiceProvider",
    "Router",
    "RoutingError",
    "Scope",
    "ServerErrorException",
    "ServiceProvider",
    "SessionGuard",
    "ShutdownError",
    "Str",
    "Throttle",
    "ThrottleException",
    "UnauthenticatedException",
    "UserResolver",
    "ValidationException",
    "VerifyCsrf",
    "__version__",
    "config",
    "dep",
    "env",
    "serve",
    "url",
    "wants_json",
]
