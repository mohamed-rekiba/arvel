"""Arvel — the Laravel of Python.

Public API surface for foundations and the HTTP layer.
See ``docs/api/foundations-api.md`` and ``docs/api/http-api.md`` for the contract.
Symbols not in ``__all__`` are internal and may change without notice.
"""

from __future__ import annotations

from fastapi import FastAPI as _FastAPI
from starlette.types import Lifespan as _StarletteLifespan

from arvel.application import Application, ApplicationBuilder, BootError, ShutdownError, serve
from arvel.config import ConfigError, ConfigNotRegisteredError, NoPrefix, config
from arvel.container import (
    AsyncBindingError,
    BindingResolutionError,
    CircularDependencyError,
    Container,
    Scope,
)
from arvel.dep import dep
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

ASGIApp = _FastAPI
"""Runtime type of the framework's HTTP ASGI app.

The current implementation is `fastapi.FastAPI`. App code should reference
`arvel.ASGIApp` rather than importing FastAPI directly, so the underlying
ASGI framework stays an internal implementation detail.
"""

HttpLifespan = _StarletteLifespan[_FastAPI]
"""Type of a lifespan callable accepted by `Application.into_asgi(lifespan=...)`.

Use the `@asynccontextmanager` decorator on an `async def lifespan(asgi_app:
ASGIApp) -> AsyncGenerator[None]` to satisfy this type.
"""

__version__ = "0.6.0"  # x-release-please-version

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
