"""HTTP service provider — binds Router, HttpExceptionHandler, default rate-limit store."""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

from arvel.console._subsystem import CliSubsystem
from arvel.http.exceptions import ExceptionTranslator, HttpExceptionHandler
from arvel.http.ratelimit import InMemoryStore, RateLimiterStore
from arvel.maintenance import MaintenanceModeManager
from arvel.providers.service_provider import ServiceProvider
from arvel.routing import Router


class HttpServiceProvider(ServiceProvider):
    """Bind every HTTP-layer service the rest of the framework expects."""

    subsystem: ClassVar[CliSubsystem | None] = CliSubsystem.HTTP

    def register(self) -> None:
        c = self.app.container
        c.singleton(Router, lambda: Router.singleton())
        c.singleton(
            HttpExceptionHandler,
            lambda: HttpExceptionHandler(translators=default_translators()),
        )
        c.singleton(RateLimiterStore, InMemoryStore)
        c.singleton(MaintenanceModeManager, lambda: MaintenanceModeManager())


def default_translators() -> Mapping[type[Exception], ExceptionTranslator]:
    """Foreign-exception translators wired into the default `HttpExceptionHandler`.

    Lives in the providers layer because it imports `arvel.http` plus the
    optional `arvel.database` / `arvel.auth` packages — the HTTP package itself
    stays ORM- and auth-agnostic. Each upstream import is optional;
    when a package isn't importable its translators are simply absent and apps
    fall back to the generic 500 envelope for those errors.
    """
    from arvel.http.exceptions import (
        AuthorizationException,
        NotFoundException,
        UnauthenticatedException,
    )

    translators: dict[type[Exception], ExceptionTranslator] = {}

    try:
        from arvel.database.exceptions import ModelNotFoundError
    except ImportError:
        pass
    else:
        translators[ModelNotFoundError] = lambda exc: NotFoundException(str(exc))

    try:
        from arvel.auth.exceptions import (
            AuthorizationException as AuthAuthorizationException,
        )
        from arvel.auth.exceptions import (
            UnauthenticatedException as AuthUnauthenticatedException,
        )
    except ImportError:
        pass
    else:
        # The auth layer raises these without knowing HTTP; map them to the
        # standard 401/403 envelopes instead of leaking a 500.
        translators[AuthUnauthenticatedException] = lambda exc: UnauthenticatedException(
            str(exc) or "Unauthenticated."
        )
        translators[AuthAuthorizationException] = lambda exc: AuthorizationException(
            str(exc) or "This action is unauthorized."
        )

    return translators


__all__ = ["HttpServiceProvider", "default_translators"]
