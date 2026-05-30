"""HTTP service provider — binds Router, HttpExceptionHandler, default rate-limit store."""

from __future__ import annotations

from collections.abc import Mapping

from arvel.http.exceptions import ExceptionTranslator, HttpException, HttpExceptionHandler
from arvel.http.ratelimit import InMemoryStore, RateLimiterStore
from arvel.maintenance import MaintenanceModeManager
from arvel.providers.service_provider import ServiceProvider
from arvel.routing import Router


class HttpServiceProvider(ServiceProvider):
    """Bind every HTTP-layer service the rest of the framework expects."""

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

    Lives in the providers layer because it imports both `arvel.http` and
    `arvel.database` — the HTTP package itself stays ORM-agnostic (ADR-016).
    `arvel.database` is optional; when it's not importable the mapping is
    empty and apps fall back to the generic 500 envelope for unhandled ORM
    errors.
    """
    from arvel.http.exceptions import NotFoundException

    try:
        from arvel.database.exceptions import ModelNotFoundError
    except ImportError:
        return {}

    def _model_not_found(exc: Exception) -> HttpException:
        return NotFoundException(str(exc))

    return {ModelNotFoundError: _model_not_found}


__all__ = ["HttpServiceProvider", "default_translators"]
