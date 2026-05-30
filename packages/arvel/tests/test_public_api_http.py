"""HTTP layer public API surface stability (FR-002-* + NFR-002-007).

Imports MUST succeed for every name we promise in http-api.md.
Stage 3b makes these tests pass.
"""

from __future__ import annotations

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# NFR-002-007 — Backward compatibility: every WI-001 symbol still works.
# ─────────────────────────────────────────────────────────────────────────────


def test_foundations_top_level_exports_still_present() -> None:
    import arvel

    foundations = {
        "Container",
        "Scope",
        "BindingResolutionError",
        "CircularDependencyError",
        "AsyncBindingError",
        "Application",
        "ApplicationBuilder",
        "BootError",
        "ShutdownError",
        "ServiceProvider",
        "ConfigError",
        "ConfigNotRegisteredError",
        "env",
        "dep",
    }
    missing = foundations - set(arvel.__all__)
    assert not missing, f"WI-001 symbols missing from arvel.__all__: {sorted(missing)}"


def test_foundations_providers_still_importable() -> None:
    from arvel.providers import ConfigServiceProvider, ServiceProvider

    assert ServiceProvider is not None
    assert issubclass(ConfigServiceProvider, ServiceProvider)


# ─────────────────────────────────────────────────────────────────────────────
# FR-002-* — New WI-002 public symbols
# ─────────────────────────────────────────────────────────────────────────────


def test_http_top_level_exports_complete() -> None:
    import arvel

    expected = {
        # routing
        "Route",
        "Router",
        "RouteServiceProvider",
        # http
        "Controller",
        "FormRequest",
        "JsonResource",
        "ResourceCollection",
        "Middleware",
        "Guard",
        "wants_json",
        # guards
        "SessionGuard",
        "JwtGuard",
        "UserResolver",
        # middleware
        "Cors",
        "Throttle",
        "Authenticate",
        "VerifyCsrf",
        # ratelimit
        "RateLimiterStore",
        "InMemoryStore",
        "RedisStore",
        "Attempt",
        # exceptions
        "HttpException",
        "BadRequestException",
        "ValidationException",
        "UnauthenticatedException",
        "AuthorizationException",
        "NotFoundException",
        "MethodNotAllowedException",
        "ConflictException",
        "ThrottleException",
        "ServerErrorException",
        "HttpExceptionHandler",
        # provider
        "HttpServiceProvider",
        # config
        "NoPrefix",
        # entrypoint
        "serve",
    }
    missing = expected - set(arvel.__all__)
    assert not missing, f"Missing HTTP exports: {sorted(missing)}"


def test_routing_module_imports() -> None:
    from arvel.routing import Route, Router, RouteServiceProvider

    assert Route is not None
    assert Router is not None
    assert RouteServiceProvider is not None


def test_http_controller_import() -> None:
    from arvel.http.controller import Controller

    assert Controller is not None


def test_http_requests_import() -> None:
    from arvel.http.requests import FormRequest

    assert FormRequest is not None


def test_http_resources_imports() -> None:
    from arvel.http.resources import JsonResource, ResourceCollection, ResourceResponse

    assert JsonResource is not None
    assert ResourceCollection is not None
    assert ResourceResponse is not None


def test_http_middleware_imports() -> None:
    from arvel.http.middleware import (
        Authenticate,
        Cors,
        Middleware,
        Throttle,
        VerifyCsrf,
    )

    assert Middleware is not None
    assert Cors is not None
    assert Throttle is not None
    assert Authenticate is not None
    assert VerifyCsrf is not None


def test_http_auth_imports() -> None:
    from arvel.http.auth import Guard, JwtGuard, SessionGuard, UserResolver

    assert Guard is not None
    assert SessionGuard is not None
    assert JwtGuard is not None
    assert UserResolver is not None


def test_http_exceptions_imports() -> None:
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

    for cls in (
        BadRequestException,
        ValidationException,
        UnauthenticatedException,
        AuthorizationException,
        NotFoundException,
        MethodNotAllowedException,
        ConflictException,
        ThrottleException,
        ServerErrorException,
    ):
        assert issubclass(cls, HttpException), f"{cls.__name__} is not HttpException"
    assert HttpExceptionHandler is not None


def test_http_negotiation_import() -> None:
    from arvel.http.negotiation import wants_json

    assert callable(wants_json)


def test_http_ratelimit_imports() -> None:
    from arvel.http.ratelimit import (
        Attempt,
        InMemoryStore,
        RateLimiterStore,
        RedisStore,
    )

    assert RateLimiterStore is not None
    assert InMemoryStore is not None
    assert RedisStore is not None
    assert Attempt is not None


def test_http_provider_import() -> None:
    from arvel.providers import HttpServiceProvider

    assert HttpServiceProvider is not None


def test_no_prefix_import() -> None:
    from arvel.config import NoPrefix

    assert NoPrefix is not None


def test_serve_import() -> None:
    from arvel import serve

    assert callable(serve)


@pytest.mark.parametrize(
    "name",
    [
        "Route",
        "Router",
        "RouteServiceProvider",
        "Controller",
        "FormRequest",
        "JsonResource",
        "ResourceCollection",
        "Middleware",
        "Guard",
        "wants_json",
        "SessionGuard",
        "JwtGuard",
        "UserResolver",
        "Cors",
        "Throttle",
        "Authenticate",
        "VerifyCsrf",
        "RateLimiterStore",
        "InMemoryStore",
        "RedisStore",
        "Attempt",
        "HttpException",
        "BadRequestException",
        "ValidationException",
        "UnauthenticatedException",
        "AuthorizationException",
        "NotFoundException",
        "MethodNotAllowedException",
        "ConflictException",
        "ThrottleException",
        "ServerErrorException",
        "HttpExceptionHandler",
        "HttpServiceProvider",
        "NoPrefix",
        "serve",
    ],
)
def test_each_http_symbol_resolves(name: str) -> None:
    import arvel

    assert hasattr(arvel, name), f"arvel.{name} not exported"
